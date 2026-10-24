#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""E08-6 edit/build/run/reboot integration gate; guest work requires --run-guest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]

from boot_smoke import Guest
from gcc_seed_smoke import import_manifest_files, sha
from make_work_disk import create_fat32
from process_smoke import command, resources
from seed_diagnostics import diagnose, guest_command
from seed_preflight import validate_bundle
from task_smoke import pump, send_bytes
from work_disk import transfer


LANGUAGES = ("c", "cpp")
FIXTURES = ROOT / "tests/fixtures/e08_integration"
EDITED_MAIN = {
    "c": b'#include <stdio.h>\n#include "project.h"\nint main(void) {\n'
         b'    int value = project_adjust(20, 22);\n'
         b'    printf("%s_V2_%d\\n", project_label(), value);\n'
         b'    return value == 42 ? 0 : 1;\n}\n',
    "cpp": b'#include "project.hpp"\nextern "C" int puts(const char *text);\n'
           b'int main() {\n'
           b'    const std::string message = project_label() + "_V2_" +\n'
           b'                                std::to_string(project_adjust(20, 22));\n'
           b'    puts(message.c_str());\n    return 0;\n}\n',
}


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def args_for_language(args: argparse.Namespace, language: str) -> tuple[Path, Path, Path, Path]:
    values = tuple(getattr(args, f"{language}_{name}") for name in
                   ("seed_manifest", "seed_root", "sysroot_manifest", "sysroot_root"))
    if any(value is None for value in values):
        raise ValueError(f"--language {language} requires all --{language}-seed-manifest/root and --{language}-sysroot-manifest/root arguments")
    return values  # type: ignore[return-value]


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=("c", "cpp", "all"), default="all")
    parser.add_argument("--run-guest", action="store_true", help="create a temporary disk and run XOS; default only preflights")
    parser.add_argument("--guest-sysroot-root", default="/sysroot")
    parser.add_argument("--image", type=Path, default=ROOT / "build/xos.img")
    parser.add_argument("--system-manifest", type=Path, default=ROOT / "build/manifest.json")
    parser.add_argument("--report", type=Path, help="explicit JSON report path; stdout if omitted")
    for language in LANGUAGES:
        parser.add_argument(f"--{language}-seed-manifest", type=Path)
        parser.add_argument(f"--{language}-seed-root", type=Path)
        parser.add_argument(f"--{language}-sysroot-manifest", type=Path)
        parser.add_argument(f"--{language}-sysroot-root", type=Path)
    args = parser.parse_args()
    if args.run_guest and args.report is None:
        parser.error("--run-guest requires --report so failures remain reviewable")
    return args


def collect_groups(args: argparse.Namespace, report: dict[str, Any]) -> list[dict[str, Any]]:
    selected = LANGUAGES if args.language == "all" else (args.language,)
    groups = []
    for language in selected:
        seed_path, seed_root, sysroot_path, sysroot_root = args_for_language(args, language)
        seed = read_json(seed_path)
        sysroot = read_json(sysroot_path)
        tools_required = (("gcc", "cc1", "as", "ld", "ar", "ranlib") if language == "c"
                          else ("g++", "cc1plus", "as", "ld", "ar", "ranlib"))
        preflight = validate_bundle(seed_path, seed_root, sysroot_path, sysroot_root,
                                    args.guest_sysroot_root, tools_required)
        record = {"language": language, "seed_manifest": str(seed_path),
                  "seed_manifest_sha256": sha(seed_path), "seed_root": str(seed_root),
                  "sysroot_manifest": str(sysroot_path),
                  "sysroot_manifest_sha256": sha(sysroot_path), "sysroot_root": str(sysroot_root),
                  "sdk_manifest": seed.get("sdk_manifest"),
                  "sdk_manifest_sha256": seed.get("sdk_manifest_sha256") or
                  (seed.get("sdk_manifest", {}).get("sha256") if isinstance(seed.get("sdk_manifest"), dict) else None),
                  "preflight": preflight.to_dict()}
        report["languages"][language] = record
        if not preflight.ok:
            report["status"] = "failed_preflight"
        groups.append({"language": language, "seed": seed, "sysroot": sysroot,
                       "seed_root": seed_root, "sysroot_root": sysroot_root,
                       "preflight": preflight, "record": record})
    return groups


def merge_file_rows(groups: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    merged: dict[str, tuple[str, dict[str, Any], Path, str]] = {}
    for group in groups:
        if kind == "seed":
            rows = group["seed"].get("install_files", [])
            root = group["seed_root"]
        else:
            rows = group["sysroot"].get("files", [])
            root = group["sysroot_root"]
        if not isinstance(rows, list):
            raise ValueError(f"{kind} manifest has no file list")
        for row in rows:
            guest = row.get("guest_path") if isinstance(row, dict) else None
            digest = row.get("sha256") if isinstance(row, dict) else None
            if not guest or not digest:
                raise ValueError(f"{kind} manifest entry needs guest_path and sha256")
            previous = merged.get(guest)
            if previous:
                if previous[0] != digest:
                    raise ValueError(f"conflicting {kind} files map to {guest}")
                continue
            merged[guest] = (digest, row, root, group["language"])
    grouped: dict[tuple[Path, str], list[dict[str, Any]]] = {}
    for _guest, (_digest, row, root, language) in merged.items():
        grouped.setdefault((root, language), []).append(row)
    # The caller imports by source root; retain that association in a private list wrapper.
    return [{"root": root, "language": language, "entries": entries}
            for (root, language), entries in grouped.items()]


def import_groups(disk: Path, groups: list[dict[str, Any]], kind: str) -> dict[str, dict[str, Any]]:
    imported: dict[str, dict[str, Any]] = {}
    for group in merge_file_rows(groups, kind):
        imported.update(import_manifest_files(disk, group["root"], group["entries"],
                                             f"{group['language']} {kind}"))
    return imported


def source_inputs(disk: Path, language: str) -> tuple[dict[str, str], dict[str, bytes]]:
    root = FIXTURES / language
    hashes: dict[str, str] = {}
    contents: dict[str, bytes] = {}
    for source in sorted(root.iterdir()):
        if not source.is_file():
            continue
        guest_path = f"/src/{language}/{source.name}"
        transfer(disk, "import", guest_path, source)
        data = source.read_bytes()
        hashes[guest_path] = digest_bytes(data)
        contents[guest_path] = data
    return hashes, contents


def boot_guest(image: Path, disk: Path, name: str) -> Guest:
    guest = Guest(image, name, work_disk=disk)
    guest.expect(b"xos64> ", timeout=25)
    send_bytes(guest, b"run\r")
    guest.expect(b"sup> ", timeout=25)
    pump(guest, 1.5)
    return guest


def edit_source(guest: Guest, language: str, baseline: tuple[int, ...], report: dict[str, Any]) -> None:
    path = f"/src/{language}/main.{language if language == 'c' else 'cpp'}"
    before = resources(guest)
    if before != baseline:
        raise AssertionError(f"resources differ before editor: {before} != {baseline}")
    start = len(guest.output)
    send_bytes(guest, f"edit {path}\r".encode("ascii"))
    guest.expect(f"[edit] {path} bytes=".encode("ascii"), start=start, timeout=15)
    guest.expect(b"| ", start=start, timeout=15)
    clear_start = len(guest.output)
    send_bytes(guest, b":c\r")
    guest.expect(b"[edit] buffer cleared", start=clear_start, timeout=10)
    guest.expect(b"| ", start=clear_start, timeout=10)
    for line in EDITED_MAIN[language].decode("ascii").splitlines():
        if len(line) > 150:
            raise AssertionError("fixture line exceeds editor input limit")
        line_start = len(guest.output)
        send_bytes(guest, line.encode("ascii") + b"\r")
        guest.expect(b"| ", start=line_start, timeout=10)
    save_start = len(guest.output)
    send_bytes(guest, b":wq\r")
    guest.expect(b"[edit] saved " + path.encode("ascii"), start=save_start, timeout=15)
    guest.expect(b"sup> ", start=save_start, timeout=15)
    after = resources(guest)
    if before != baseline or after != baseline:
        raise AssertionError(f"editor operation changed resources: before={before}, after={after}, baseline={baseline}")
    report["commands"].append({"language": language, "kind": "supervisor_editor",
                               "path": path, "saved_sha256": digest_bytes(EDITED_MAIN[language]),
                               "resources": after})


def run_guest_command(guest: Guest, language: str, line: str, compiler_paths: tuple[str, ...],
                      baseline: tuple[int, ...], report: dict[str, Any], *,
                      expected_output: bytes | None = None, timeout: int = 240,
                      require_marker: bytes | None = None) -> bytes:
    supervisor_line = guest_command(line, compiler_paths)
    start_time = time.monotonic()
    output = command(guest, supervisor_line, b"sup> ", timeout=timeout)
    match = re.search(rb"kind=exited code=(-?\d+)", output)
    if match is None or int(match.group(1)) != 0:
        raise AssertionError(f"{supervisor_line} did not exit successfully: {output[-2500:]!r}")
    if expected_output is not None and expected_output not in output:
        raise AssertionError(f"{supervisor_line} missing output {expected_output!r}: {output[-2500:]!r}")
    if require_marker is not None and require_marker not in output:
        raise AssertionError(f"{supervisor_line} missing driver marker {require_marker!r}: {output[-2500:]!r}")
    diagnostic = diagnose(output, supervisor_line)
    if diagnostic["host_path_leaks"]:
        raise AssertionError(f"host paths leaked into guest compiler invocation: {diagnostic['host_path_leaks']}")
    current = resources(guest)
    if current != baseline:
        raise AssertionError(f"resource drift after {supervisor_line}: {current} != {baseline}")
    report["commands"].append({"language": language, "line": line,
                               "supervisor_command": supervisor_line,
                               "exit_code": int(match.group(1)),
                               "elapsed_seconds": time.monotonic() - start_time,
                               "diagnostic": diagnostic,
                               "resources": current,
                               "output": output.decode("ascii", errors="replace")})
    report["resource_samples"].append({"language": language, "line": line,
                                      "resources": current})
    return output


def compile_project(guest: Guest, language: str, seed: dict[str, Any],
                    baseline: tuple[int, ...], report: dict[str, Any], phase: str) -> tuple[str, str]:
    compiler_name = "gcc" if language == "c" else "g++"
    compiler = seed["tools"][compiler_name]["guest_path"]
    ar = seed["tools"]["ar"]["guest_path"]
    ranlib = seed["tools"]["ranlib"]["guest_path"]
    compiler_paths = (compiler,)
    standard = "-std=c11" if language == "c" else "-std=gnu++17"
    common = f"{compiler} -v {standard} -static --sysroot=/sysroot -I/src/{language}"
    lib_source = "project.c" if language == "c" else "project.cpp"
    adjust_source = "adjust.c" if language == "c" else "adjust.cpp"
    main_source = "main.c" if language == "c" else "main.cpp"
    stem = f"{language}_{phase}"
    run_guest_command(guest, language,
                      f"{common} -c /src/{language}/{lib_source} -o /out/{stem}_project.o",
                      compiler_paths, baseline, report, timeout=300,
                      require_marker=b"cc1")
    archive_name = f"lib{stem}.a"
    run_guest_command(guest, language,
                      f"{ar} rcS /out/{archive_name} /out/{stem}_project.o",
                      compiler_paths, baseline, report, timeout=180)
    run_guest_command(guest, language,
                      f"{ranlib} /out/{archive_name}",
                      compiler_paths, baseline, report, timeout=180)
    for source, object_name in ((adjust_source, f"{stem}_adjust.o"),
                                (main_source, f"{stem}_main.o")):
        run_guest_command(guest, language,
                          f"{common} -c /src/{language}/{source} -o /out/{object_name}",
                          compiler_paths, baseline, report, timeout=300)
    app = f"/out/{language}_app.elf"
    run_guest_command(guest, language,
                      f"{compiler} -v -static --sysroot=/sysroot /out/{stem}_main.o "
                      f"/out/{stem}_adjust.o -L/out -l{stem} -o {app}",
                      compiler_paths, baseline, report, timeout=360, require_marker=b"ld")
    return app, archive_name


def run_application(guest: Guest, language: str, app: str,
                    compiler_paths: tuple[str, ...], baseline: tuple[int, ...],
                    report: dict[str, Any], version: int) -> None:
    marker = (b"E08_INTEGRATION_C_V" + str(version).encode() + b"_42" if language == "c"
              else b"E08_INTEGRATION_CPP_V" + str(version).encode() + b"_42")
    run_guest_command(guest, language, app, compiler_paths, baseline, report,
                      expected_output=marker, timeout=90)


def main() -> int:
    args = cli()
    selected = LANGUAGES if args.language == "all" else (args.language,)
    report: dict[str, Any] = {"schema_version": 1, "gate": "E08-6",
                              "status": "not_run", "guest_execution": "not_run",
                              "e08_complete": False,
                              "language_selection": list(selected), "languages": {},
                              "commands": [], "resource_samples": [], "outputs": {},
                              "checks": [], "limitations": [
                                  "single-language runs are partial E08-6 evidence, not full E08 completion",
                                  "this gate does not repeat the E08-4/5 feature matrix or stress/soak tests"]}
    guests: list[Guest] = []
    temporary = None
    try:
        groups = collect_groups(args, report)
        if report["status"] == "failed_preflight":
            raise ValueError("one or more Seed/sysroot preflights failed")
        report["status"] = "prepared_not_run"
        if not args.run_guest:
            report["guest_execution"] = "not_run"
            print(json.dumps(report, indent=2, sort_keys=True))
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
            return 0

        if args.guest_sysroot_root != "/sysroot":
            # The fixed Seed driver specs use /sysroot; reject a contradictory override.
            raise ValueError("E08-6 driver command contract currently requires guest sysroot /sysroot")
        for group in groups:
            for row in group["seed"].get("install_files", []) + group["sysroot"].get("files", []):
                guest_path = row.get("guest_path", "")
                if any(ord(char) < 33 or ord(char) > 126 for char in guest_path):
                    raise ValueError(f"guest path cannot be transferred by the current disk helper: {guest_path!r}")

        system_manifest = read_json(args.system_manifest)
        image = args.image.resolve(strict=True)
        image_hash = sha(image)
        recorded_image_hash = system_manifest.get("artifacts", {}).get("xos.img", {}).get("sha256")
        if recorded_image_hash != image_hash:
            raise ValueError("XOS image hash does not match the explicit system manifest")
        report.update({"guest_execution": "running", "image": str(image),
                       "image_sha256": image_hash,
                       "system_manifest": str(args.system_manifest),
                       "system_manifest_sha256": sha(args.system_manifest),
                       "build_id": system_manifest.get("build_id"),
                       "machine": "pc-i440fx / qemu64 / TCG / 512 MiB"})
        temporary = tempfile.TemporaryDirectory(prefix="xos_e08_6_")
        work = Path(temporary.name)
        disk = work / "work.img"
        create_fat32(disk, 2048)
        for directory in ("/bin", "/src", "/src/c", "/src/cpp", "/out", "/tmp"):
            transfer(disk, "mkdir", directory)
        seed_inputs = import_groups(disk, groups, "seed")
        sysroot_inputs = import_groups(disk, groups, "sysroot")
        report["seed_inputs"] = seed_inputs
        report["sysroot_inputs"] = sysroot_inputs
        report["fixtures"] = {}
        fixture_originals: dict[str, bytes] = {}
        for language in selected:
            hashes, contents = source_inputs(disk, language)
            report["fixtures"][language] = hashes
            fixture_originals.update(contents)
        guests.append(boot_guest(image, disk, "e08_6_boot1"))
        report["qemu_command"] = guests[-1].command

        for phase, expected_version in (("initial", 1), ("edited", 2)):
            if phase == "edited":
                for language in selected:
                    active_guest = guests[-1]
                    baseline = resources(active_guest)
                    edit_source(active_guest, language, baseline, report)
            for language in selected:
                guest = guests[-1]
                baseline = resources(guest)
                seed = next(group["seed"] for group in groups if group["language"] == language)
                compiler = seed["tools"]["gcc" if language == "c" else "g++"]["guest_path"]
                app, archive = compile_project(guest, language, seed, baseline, report, phase)
                run_application(guest, language, app, (compiler,), baseline, report, expected_version)
                record = report["languages"][language]
                record.setdefault("applications", []).append(app)
                record.setdefault("archives", []).append("/out/" + archive)
                report["checks"].append(f"{language}_{phase}_multi_tu_static_library_compile_and_run")
        guest = guests[-1]
        baseline = resources(guest)
        command(guest, "sync", b"[files] sync=ok", timeout=60)
        report["commands"].append({"kind": "sync", "resources": resources(guest)})
        if resources(guest) != baseline:
            raise AssertionError("sync changed task/page/completion resource counters")
        guest.close()
        guests.pop()

        # Reboot the same image; the final edited binaries and sources must survive.
        reboot_guest = boot_guest(image, disk, "e08_6_reboot")
        guests.append(reboot_guest)
        reboot_baseline = resources(reboot_guest)
        for language in selected:
            compiler = next(group["seed"]["tools"]["gcc" if language == "c" else "g++"]["guest_path"]
                            for group in groups if group["language"] == language)
            run_application(reboot_guest, language, f"/out/{language}_app.elf",
                            (compiler,), reboot_baseline, report, 2)
            report["checks"].append(f"{language}_edited_application_survives_sync_and_reboot")
        sync_output = command(reboot_guest, "sync", b"[files] sync=ok", timeout=60)
        report["commands"].append({"kind": "reboot_sync", "output": sync_output.decode(errors="replace"),
                                   "resources": resources(reboot_guest)})
        reboot_guest.close()
        guests.pop()

        # Offline reads begin only after the last QEMU process has closed.
        for guest_path, original in fixture_originals.items():
            exported = work / ("source_" + guest_path.rsplit("/", 1)[-1] + "_" + str(len(guest_path)))
            transfer(disk, "export", guest_path, exported)
            expected = EDITED_MAIN["c" if "/c/" in guest_path else "cpp"] if guest_path.endswith(("main.c", "main.cpp")) else original
            if exported.read_bytes() != expected:
                raise AssertionError(f"source persistence mismatch after editor/reboot: {guest_path}")
            report["outputs"][guest_path] = {"bytes": exported.stat().st_size,
                                             "sha256": sha(exported), "persisted": True}
        for group in groups:
            for tool_name, tool in group["seed"].get("tools", {}).items():
                guest_path = tool.get("guest_path")
                if not guest_path:
                    raise ValueError(f"tools.{tool_name} needs an explicit guest_path for integrity export")
                export_path = work / ("tool_" + re.sub(r"[^A-Za-z0-9_.-]", "_", tool_name) + "_" + str(len(guest_path)))
                transfer(disk, "export", guest_path, export_path)
                actual = sha(export_path)
                if actual != tool["sha256"]:
                    raise AssertionError(f"guest modified tool input {tool_name}: {guest_path}")
                report["outputs"].setdefault("tool_integrity", {})[guest_path] = actual
        for language in selected:
            names = [Path(item).name for item in report["languages"][language].get("archives", [])]
            names.append(f"{language}_app.elf")
            for name in names:
                export_path = work / ("artifact_" + name)
                transfer(disk, "export", "/out/" + name, export_path)
                report["outputs"]["/out/" + name] = {"bytes": export_path.stat().st_size,
                                                       "sha256": sha(export_path)}
        report["checks"].append("sources_persist_and_seed_tools_remain_byte_identical_after_qemu_closed")
        report["guest_execution"] = "passed"
        report["status"] = "passed" if set(selected) == set(LANGUAGES) else "passed_partial_language"
        report["e08_complete"] = False
        print(f"PASS: E08-6 integration languages={','.join(selected)}; status={report['status']}")
        return 0
    except Exception as exc:
        if report.get("status") != "failed_preflight":
            report["status"] = "failed"
        report["error"] = str(exc)
        print(f"FAIL: {exc}", file=sys.stderr)
        if args.report is None:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 1
    finally:
        for guest in reversed(guests):
            guest.close()
        if temporary is not None:
            temporary.cleanup()
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
