#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Boot the same Qt Quick ELF with two independently deployed loose QML palettes."""

import argparse
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from boot_smoke import Guest
from graphics_guest import start_graphics, stop_graphics
from process_smoke import resources
from qt6_quick_guest import digest, scanout, stroke
from shell_launch_support import bind_system
from task_smoke import pump, send_bytes

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from make_work_disk import create_fat32
from xypm_format import canonical, load_json, require
from xypm_image import Disk
from xypm_sdk_profile import relative_file, sdk_snapshot

PROJECT = ROOT / "tests/fixtures/qt6/quick_external"
DEPLOYMENT = "/usr/share/quick-file"
EXECUTABLE = "/bin/quick-file.elf"
CASES = (("mint", "scene/ScenePalette.qml", "35c29d", "f0a945"),
         ("violet", "alternate/ScenePalette.qml", "a070f0", "5dd6f5"))


def boot_image(image, disk, output, tag, initial, active, result):
    guest = Guest(image, "quick_file", work_disk=disk, log_dir=output)
    try:
        result["qemu_version"] = subprocess.check_output(
            [guest.command[0], "--version"], text=True).splitlines()[0]
        guest.expect(b"xos64> ", timeout=40)
        send_bytes(guest, b"run\r")
        guest.expect_supervisor(trace=True, timeout=40)
        pump(guest, 1.5)
        result["baseline"] = resources(guest)
        graphics = start_graphics(guest)
        result["with_graphics"] = resources(guest)
        start = len(guest.output)
        send_bytes(guest, f"exec-file {EXECUTABLE}\r".encode())
        frame = f"QT_QUICK_FILE_FRAME tag={tag}".encode()
        first = guest.expect_any((frame, b"kind=exited", b"kind=faulted", b"xsh> "),
                                 start=start, timeout=120)
        require(first == frame, "Quick application returned before its first frame")
        result["initial"] = scanout(guest, output / "initial.ppm", initial)
        stroke(guest, "a")
        guest.expect(f"QT_QUICK_FILE_STATE tag={tag} state=active".encode(), start=start)
        result["active"] = scanout(guest, output / "active.ppm", active)
        stroke(guest, "b")
        guest.expect(b"QT_QUICK_FILE_OK", start=start)
        guest.expect(b"kind=exited code=0", start=start)
        guest.expect_supervisor(start=start)
        require(b"input-thread-joined" in guest.output[start:], "Quick input thread did not exit")
        result["after_payload"] = resources(guest)
        require(result["after_payload"] == result["with_graphics"], "Quick payload leaked resources")
        stop_graphics(guest, *graphics)
        result["after_services"] = resources(guest)
        require(result["after_services"] == result["baseline"], "Quick graphics services leaked resources")
    finally:
        guest.close()
        result["serial_sha256"] = digest(output / "quick_file_serial.log")


def run_cases(image, elf, output, cases):
    with TemporaryDirectory(prefix="xos_quick_file_") as temporary:
        work = Path(temporary)
        for tag, palette, initial, active in CASES:
            disk = work / f"{tag}.img"
            create_fat32(disk, 512)
            deployed = {EXECUTABLE: elf, f"{DEPLOYMENT}/Scene.qml": PROJECT / "scene/Scene.qml",
                        f"{DEPLOYMENT}/ScenePalette.qml": PROJECT / palette}
            expected = {name: digest(path) for name, path in deployed.items()}
            with Disk(disk, work) as mounted:
                for folder in ("/bin", "/usr", "/usr/share", DEPLOYMENT):
                    mounted.command("mkdir", folder)
                for name, path in deployed.items():
                    mounted.command("import", name, path)
                readback = {name: digest(mounted.export(name)) for name in deployed}
            require(readback == expected, "Loose QML or the executable changed during FAT deployment")
            result = {"fat_files": readback, "colors": [initial, active]}
            cases[tag] = result
            case_output = output / tag
            case_output.mkdir()
            boot_image(image, disk, case_output, tag, initial, active, result)
            with Disk(disk, work, read_only=True) as mounted:
                require({name: digest(mounted.export(name)) for name in deployed} == expected,
                        "Qt Quick changed a deployed file")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("system", "kit", "app-receipt", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--system-source", type=Path, default=ROOT)
    args = parser.parse_args()
    system = bind_system(args.system, args.system_source)
    image = args.system / "xos-install.iso"
    kit_file = args.kit / "manifest.json"
    kit = load_json(kit_file)
    target_file = args.kit / "target_receipt.json"
    profile = args.kit / "runtime/profile.json"
    sdk_manifest = args.kit / "runtime/sdk/manifest.json"
    app = load_json(args.app_receipt)
    elf = relative_file(args.app_receipt.parent.resolve(), app["elf"])
    require(app["status"] == "static_quick_application_linked"
            and app["elf_sha256"] == digest(elf)
            and app["qt_inputs"] == kit["qt_inputs"]
            and app["kit_manifest_sha256"] == digest(kit_file)
            and app["target_receipt_sha256"] == kit["target_receipt_sha256"] == digest(target_file)
            and app["sdk_manifest_sha256"] == kit["sdk_manifest_sha256"] == digest(sdk_manifest)
            and app["sdk_profile_file_sha256"] == kit["sdk_profile_file_sha256"] == digest(profile)
            and app["app_source_tree_sha256"] == sdk_snapshot(PROJECT)[0],
            "Expected the bound external-file Qt Quick fixture")

    output = args.output.resolve()
    output.mkdir(parents=True)
    report = {"status": "failed", "cases": {}, "elf_sha256": digest(elf),
              "app_receipt_sha256": digest(args.app_receipt), "kit_manifest_sha256": digest(kit_file),
              "sdk_manifest_sha256": digest(sdk_manifest), "profile_sha256": digest(profile),
              "target_receipt_sha256": digest(target_file), "system_build_id": system["build_id"],
              "system_manifest_sha256": digest(args.system / "manifest.json"), "iso_sha256": digest(image)}
    try:
        run_cases(image, elf, output, report["cases"])
        report["status"] = "passed"
    finally:
        (output / "report.json").write_bytes(canonical(report))


if __name__ == "__main__":
    main()
