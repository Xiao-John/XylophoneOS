# SPDX-License-Identifier: Apache-2.0
"""Guest acceptance for the native Xshell UI and executable lookup behavior."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import struct

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from task_smoke import send_bytes, pump
from make_work_disk import create_fat32
from toolchain import COMMON_FLAGS, X86_FLAGS, tool


def command(guest, line, prompt=b"xsh> ", timeout=30):
    start = len(guest.output)
    send_bytes(guest, line.encode() + b"\r")
    guest.expect(prompt, start=start, timeout=timeout)
    return bytes(guest.output)[start:]


def resources(guest):
    output = command(guest, "stats")
    match = re.search(rb"\[resources\] free=(\d+) tasks=(\d+) completions=(\d+)", output)
    if match is None:
        raise AssertionError(f"Missing resource counters: {output!r}")
    return tuple(int(value) for value in match.groups())


def transfer(helper, disk, operation, path, source=None):
    args = [str(helper), str(disk), operation, path]
    if source is not None:
        args.append(str(source))
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)


def resolve_asset(system_dir, filename):
    candidates = (system_dir / filename, ROOT / "build" / filename)
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(f"Required ELF not found: {filename}")


def build_probe(source, sdk, output):
    compiler = tool("g++")
    obj = output.with_suffix(".o")
    subprocess.run([compiler, *COMMON_FLAGS, *X86_FLAGS, "-I", str(sdk / "include"),
                    "-c", str(source), "-o", str(obj)], check=True)
    subprocess.run([compiler, *X86_FLAGS, "-nostdlib", "-static", "-no-pie",
                    "-Wl,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096",
                    "-T", str(sdk / "user.ld"), str(sdk / "crt0.o"), str(obj),
                    "-Wl,--start-group", str(sdk / "lib/libxos.a"),
                    str(sdk / "lib/libxos_loader.a"), str(sdk / "lib/libc.a"),
                    str(sdk / "lib/libm.a"), "-lgcc", "-Wl,--end-group",
                    "-o", str(output)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    system_dir = args.system_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    image = system_dir / "xos.img"
    manifest_path = system_dir / "manifest.json"
    if not manifest_path.exists():
        manifest_path = system_dir / "system_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    image_sha256 = hashlib.sha256(image.read_bytes()).hexdigest()
    expected_image_sha256 = manifest.get("artifacts", {}).get("xos.img", {}).get("sha256")
    if expected_image_sha256 and image_sha256 != expected_image_sha256:
        raise AssertionError("system image differs from its manifest")

    dash = ROOT / ".cache/xos_seed/dash/439a3c7825a15e276be9/build/src/dash"
    fault = resolve_asset(system_dir, "user_fault.image.elf")
    sdk_dir = system_dir / "sdk"
    if not sdk_dir.is_dir():
        sdk_dir = ROOT / "build/sdk"
    if not dash.is_file():
        raise FileNotFoundError(f"Required dash ELF not found: {dash}")

    report = {
        "status": "failed", "system_dir": str(system_dir),
        "system_build_id": manifest.get("build_id"), "image_sha256": image_sha256,
        "checks": [], "baseline_resources": None,
    }
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix="xos_xsh_ui_") as temporary:
            folder = Path(temporary)
            hello_probe = output_dir / "hello_probe.elf"
            exit_probe = output_dir / "exit_17_probe.elf"
            build_probe(ROOT / "tests/fixtures/xsh_ui/hello.cpp", sdk_dir, hello_probe)
            build_probe(ROOT / "tests/fixtures/xsh_ui/exit_17.cpp", sdk_dir, exit_probe)
            diagnostic_probe = output_dir / "diagnostic_probe.elf"
            build_probe(ROOT / "tests/fixtures/xsh_ui/diagnostic.cpp", sdk_dir, diagnostic_probe)
            wrong_isa = output_dir / "wrong_isa.elf"
            wrong_bytes = bytearray(hello_probe.read_bytes())
            if wrong_bytes[:4] != b"\x7fELF" or len(wrong_bytes) < 20:
                raise AssertionError("Compiled probe is not an ELF file")
            struct.pack_into("<H", wrong_bytes, 18, 183)
            wrong_isa.write_bytes(wrong_bytes)
            disk = folder / "xsh_ui_work.img"
            create_fat32(disk, 512)
            helper = ROOT / "build/work_disk_host"
            for directory in ("/usr", "/usr/bin", "/bin", "/tests", "/tmp"):
                transfer(helper, disk, "mkdir", directory)

            # Put three non-runnable candidates ahead of a valid ELF at each later PATH slot.
            transfer(helper, disk, "import", "/usr/bin/ui_path", ROOT / "tests/fixtures/xsh_ui/ordinary_data.txt")
            transfer(helper, disk, "mkdir", "/bin/ui_path")
            transfer(helper, disk, "import", "/ui_path", hello_probe)
            transfer(helper, disk, "import", "/usr/bin/ui_data", ROOT / "tests/fixtures/xsh_ui/ordinary_data.txt")
            transfer(helper, disk, "import", "/bin/ui_data", hello_probe)
            transfer(helper, disk, "import", "/usr/bin/ui_isa", wrong_isa)
            transfer(helper, disk, "import", "/bin/ui_isa", hello_probe)
            transfer(helper, disk, "import", "/usr/bin/ui_badisa", wrong_isa)
            transfer(helper, disk, "import", "/usr/bin/ui_exit17", exit_probe)
            transfer(helper, disk, "import", "/usr/bin/ui_diagnostic", diagnostic_probe)
            transfer(helper, disk, "import", "/usr/bin/program.txt", hello_probe)
            transfer(helper, disk, "import", "/usr/bin/ui_fault", fault)
            transfer(helper, disk, "import", "/usr/bin/dash", dash)
            guest = Guest(image, "xsh_ui", work_disk=disk)
            guest.expect(b"xos64> ", timeout=40)
            send_bytes(guest, b"run\r")
            guest.expect(b"Xshell", timeout=30)
            guest.expect(b"xsh> ", timeout=20)
            initial = bytes(guest.output)
            if b"Welcome" not in initial or b"sup> " in initial:
                raise AssertionError(f"Xshell did not enter its native prompt: {initial[-2500:]!r}")
            report["checks"].append("xos64_run_enters_xshell_welcome_and_prompt")
            pump(guest, 1.5)
            baseline = resources(guest)
            report["baseline_resources"] = baseline

            quiet = command(guest, "ui_exit17")
            for forbidden in (b"[loader]", b"[wait]", b"kernel started", b"reclaimed", b"wait_blocked"):
                if forbidden in quiet:
                    raise AssertionError(f"Default successful execution was noisy ({forbidden!r}): {quiet!r}")
            if (b"xsh_ui_exit_17_ran" not in quiet or b"TRACE_DENIED=-1" not in quiet or
                    b"xsh: program exited with status 17" not in quiet):
                raise AssertionError(f"Exit 17 was not visible: {quiet!r}")
            if resources(guest) != baseline:
                raise AssertionError("Successful execution did not restore resource counters")
            report["checks"].append("silent_success_and_visible_nonzero_exit")

            trace_on = command(guest, "trace on")
            if b"xsh: trace on" not in trace_on:
                raise AssertionError(f"trace on did not acknowledge state: {trace_on!r}")
            traced = command(guest, "ui_exit17")
            for marker in (b"[loader]", b"[wait]", b"reclaimed"):
                if marker not in traced:
                    raise AssertionError(f"trace on omitted lifecycle marker {marker!r}: {traced!r}")
            if not all(marker in traced for marker in
                       (b"TRACE_DENIED=-1", b"xsh_ui_exit_17_ran", b"kind=exited code=17")):
                raise AssertionError(f"Trace changed program stdout or exit reporting: {traced!r}")
            trace_off = command(guest, "trace off")
            if b"xsh: trace off" not in trace_off:
                raise AssertionError(f"trace off did not acknowledge state: {trace_off!r}")
            quiet_again = command(guest, "ui_exit17")
            for forbidden in (b"[loader]", b"[wait]", b"reclaimed", b"wait_blocked"):
                if forbidden in quiet_again:
                    raise AssertionError(f"trace off did not restore quiet mode: {quiet_again!r}")
            if not all(marker in quiet_again for marker in
                       (b"TRACE_DENIED=-1", b"xsh_ui_exit_17_ran", b"xsh: program exited with status 17")):
                raise AssertionError(f"trace off changed program stdout or exit reporting: {quiet_again!r}")
            if resources(guest) != baseline:
                raise AssertionError("Trace toggling or repeated execution leaked resources")
            report["checks"].append("trace_toggles_lifecycle_diagnostics_without_changing_stdout")

            # PATH must skip data, directory, and wrong-machine candidates and keep searching.
            for name in ("ui_path", "ui_data", "ui_isa"):
                result = command(guest, f"{name}")
                if b"xsh_ui_path_candidate_ran" not in result or b"TRACE_DENIED=-1" not in result:
                    raise AssertionError(f"PATH did not reach later valid ELF for {name}: {result!r}")
                if resources(guest) != baseline:
                    raise AssertionError(f"PATH candidate cleanup failed for {name}")
            report["checks"].append("path_skips_data_directory_and_incompatible_elf_candidates")

            explicit = command(guest, "exec-file /usr/bin/ui_path")
            if b"not executable" not in explicit.lower() or b"xsh_ui_path_candidate_ran" in explicit:
                raise AssertionError(f"Explicit path incorrectly fell back: {explicit!r}")
            if resources(guest) != baseline:
                raise AssertionError("Explicit path rejection did not restore resources")
            report["checks"].append("explicit_path_failure_does_not_fallback")

            typed = command(guest, "type ui_path")
            if b"ui_path -> /ui_path" not in typed:
                raise AssertionError(f"type did not show resolved executable path: {typed!r}")
            builtin = command(guest, "type trace")
            if b"builtin" not in builtin.lower():
                raise AssertionError(f"type did not identify builtin: {builtin!r}")
            alias = command(guest, "type exd")
            if b"exd: alias for exec-driver" not in alias:
                raise AssertionError(f"type did not identify exd alias: {alias!r}")
            report["checks"].append("type_resolves_executable_builtin_and_exd_alias")

            for line, word, path_hint in (("exec-file ui_missing", b"not found", b"ui_missing"),
                                          ("exec-file /usr/bin/ui_data", b"not executable", b"/usr/bin/ui_data"),
                                          ("exec-file ui_badisa", b"incompatible target", b"/usr/bin/ui_badisa")):
                result = command(guest, line)
                if word not in result.lower() or path_hint not in result:
                    raise AssertionError(f"{line} missing expected error class {word!r}: {result!r}")
                if resources(guest) != baseline:
                    raise AssertionError(f"Failed lookup leaked resources for {line}")
            report["checks"].append("failed_lookup_preserves_reason_class_and_resources")

            diagnosed = command(guest, "exec-file ui_diagnostic")
            if b"DIAG_CREATE_DENIED_CLEANUP=20" not in diagnosed or resources(guest) != baseline:
                raise AssertionError(f"Structured launch denial leaked resources/handles: {diagnosed!r}")
            report["checks"].append("structured_create_denial_releases_file_handles")

            renamed = command(guest, "program.txt")
            if b"xsh_ui_path_candidate_ran" not in renamed or resources(guest) != baseline:
                raise AssertionError(f"Filename extension changed executable recognition: {renamed!r}")
            if any(marker in renamed for marker in (b"[loader]", b"[wait]", b"program exited")):
                raise AssertionError(f"Successful execution was not quiet: {renamed!r}")
            report["checks"].append("valid_elf_executes_with_data_filename_extension")

            fault_result = command(guest, "exec-file ui_fault", timeout=40)
            if b"xsh: program faulted (vector=14)" not in fault_result:
                raise AssertionError(f"Fault result was hidden: {fault_result!r}")
            if resources(guest) != baseline:
                raise AssertionError("Faulted child did not restore resources")
            report["checks"].append("fault_is_never_silenced")

            start = len(guest.output)
            send_bytes(guest, b"exd dash -i\r")
            guest.expect(b"$ ", start=start, timeout=40)
            mark = len(guest.output)
            send_bytes(guest, b"exit\r")
            guest.expect(b"xsh> ", start=mark, timeout=40)
            if resources(guest) != baseline:
                raise AssertionError("Interactive dash exit did not return to baseline resources")
            report["checks"].append("exd_dash_interactive_exit_returns_to_xshell")
            report["status"] = "passed"
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        if guest is not None:
            guest.close()
            (output_dir / "xsh_ui_serial.log").write_bytes(guest.output)
            qemu_log = ROOT / "build/xsh_ui_qemu.log"
            if qemu_log.exists():
                shutil.copy2(qemu_log, output_dir / "xsh_ui_qemu.log")
        (output_dir / "xsh_ui_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
