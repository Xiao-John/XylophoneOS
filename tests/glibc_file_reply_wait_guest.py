#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise file reply readiness and service teardown in ordinary and fault guests."""

import argparse
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from boot_smoke import Guest
from make_work_disk import create_fat32
from shell_launch_support import bind_system, check_hash, command, resources, sha
from task_smoke import send_bytes
from work_disk import transfer


def stage_disk(directory, probe, dash):
    disk = directory / "work.img"
    content = directory / "fixture"
    content.write_bytes(b"XOS-read")
    create_fat32(disk, 512)
    for path in ("/usr", "/usr/bin", "/bin"):
        transfer(disk, "mkdir", path)
    for index, (name, source) in enumerate((("/usr/bin/dash", dash), ("/bin/wait.elf", probe),
                                           ("/bin/wait.txt", content))):
        transfer(disk, "import", name, source)
        readback = directory / f"readback_{index}"
        transfer(disk, "export", name, readback)
        assert sha(readback) == sha(source)
    return disk


def run_guest(output, system, probe, dash, case_names):
    name = case_names[0]
    with TemporaryDirectory(prefix="xos_file_reply_") as temporary:
        disk = stage_disk(Path(temporary), probe, dash)
        with_serial = Guest(system / "xos-install.iso", name, work_disk=disk, log_dir=output)
        try:
            with_serial.expect(b"xos64> ", timeout=30)
            send_bytes(with_serial, b"run\r")
            with_serial.expect_supervisor(trace=True, timeout=30)
            command(with_serial, "demo quiet", b"demo tasks")
            before = resources(with_serial)
            results = []
            if name.startswith("death"):
                listing = command(with_serial, "ps", b"name=files ")
                service = re.search(rb"^pid=(\d+) name=files ", listing, re.MULTILINE)[1]
                output_text = command(with_serial, f"exec-file /bin/wait.elf {name}",
                                      b"FILE_REPLY_WAIT_PASS " + name.encode())
                freed = re.search(rb"\[task\] event=reclaimed pid=" + service + rb" pages=(\d+)", output_text)
                assert freed is not None
                assert b"kind=exited code=0" in output_text
                after = resources(with_serial)
                assert after == (before[0] + int(freed[1]), before[1] - 1, before[2])
                results.append({"case": name, "launcher": "xsh", "output": output_text.decode(),
                                "resources_after": after})
            else:
                for entry in ("xsh", "dash"):
                    for case in case_names:
                        invocation = ("exec-file /bin/wait.elf " + case if entry == "xsh"
                                      else "dash -c '/bin/wait.elf " + case + "'")
                        output_text = command(with_serial, invocation, b"FILE_REPLY_WAIT_PASS " + case.encode())
                        assert b"kind=exited code=0" in output_text
                        after = resources(with_serial)
                        assert before == after
                        results.append({"case": case, "launcher": entry, "output": output_text.decode(),
                                        "resources_after": after})
                start = len(with_serial.output)
                send_bytes(with_serial, b"exec-file /bin/wait.elf cancel\r")
                with_serial.expect(b"FILE_REPLY_WAIT_CANCEL_READY", start=start)
                send_bytes(with_serial, b"\x1b")
                with_serial.expect(b"event=cancelled_by_escape", start=start)
                with_serial.expect_supervisor(start=start)
                output_text = bytes(with_serial.output[start:]).decode()
                after = resources(with_serial)
                assert before == after and "FILE_REPLY_WAIT_FAIL" not in output_text
                results.append({"case": "cancel", "launcher": "xsh", "output": output_text,
                                "resources_after": after})
        finally:
            with_serial.close()
        return {"checks": results, "resources_before": before,
                "serial_sha256": sha(output / f"{name}_serial.log")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("system", "death-system", "sdk-manifest", "profile", "probe", "probe-receipt",
                 "dash", "dash-receipt", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"status": "failed", "checks": {}}
    try:
        normal = bind_system(args.system)
        death = bind_system(args.death_system)
        assert not normal["glibc_files_death_probe"] and death["glibc_files_death_probe"]
        sdk = json.loads(args.sdk_manifest.read_bytes())
        profile = json.loads(args.profile.read_bytes())
        probe = json.loads(args.probe_receipt.read_bytes())
        dash = json.loads(args.dash_receipt.read_bytes())
        libc_session = "src/ports/glibc/sysdeps/xos/xos_file_session.c"
        source = ROOT / "tests/fixtures/glibc_g3/file_reply_wait_probe.c"
        check_hash(ROOT / libc_session, sdk["inputs"][libc_session], "glibc file session source")
        assert set(probe["sources"].values()) == {sha(source)}
        assert probe["status"] == "static_program_linked" and dash["status"] == "built_not_run"
        sdk_sha = sha(args.sdk_manifest)
        profile_sha = sha(args.profile)
        assert profile["sdk_binding"]["sdk_manifest_sha256"] == sdk_sha
        assert probe["sdk_manifest_sha256"] == dash["sdk_manifest_sha256"] == sdk_sha
        assert probe["profile_binding"]["profile_sha256"] == dash["sdk_profile_binding"]["profile_sha256"]
        assert probe["profile_binding"]["profile_id"] == profile["id"]
        check_hash(args.probe, probe["elf_sha256"], "files readiness ELF")
        check_hash(args.dash, dash["sha256"], "Dash ELF")
        report.update({"sdk_manifest_sha256": sdk_sha, "profile_file_sha256": profile_sha,
                       "probe_receipt_sha256": sha(args.probe_receipt), "dash_receipt_sha256": sha(args.dash_receipt),
                       "probe_sha256": sha(args.probe), "dash_sha256": sha(args.dash), "builds": {
                           label: {"build_id": system_manifest["build_id"],
                                   "manifest_sha256": sha(system / "manifest.json"),
                                   "iso_sha256": sha(system / "xos-install.iso")}
                           for label, system, system_manifest in (("normal", args.system, normal),
                                                                  ("death", args.death_system, death))}})
        report["checks"]["normal"] = run_guest(args.output, args.system, args.probe, args.dash,
                                              ("normal", "concurrent"))
        for case in ("death", "death_libc"):
            report["checks"][case] = run_guest(args.output, args.death_system, args.probe, args.dash, (case,))
        report["status"] = "passed"
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS files response wait guests")


if __name__ == "__main__":
    main()
