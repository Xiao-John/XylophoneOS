#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Cold-boot the Qt Quick example after offline install, replacement and rollback."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src/ports/qt6/quick"))
from boot_smoke import Guest
from graphics_guest import start_graphics, stop_graphics
from make_work_disk import create_fat32
from pack_relinked_app import EXECUTABLE, PACKAGE_ID
from process_smoke import command, resources
from qt6_quick_kit_guest import capture_external_scene
from task_smoke import send_bytes
from xypm_format import require, sha_file, verify_package
from xypm_image import Disk, query_image, transact
from xypm_sdk_profile import metadata_snapshot

GUEST_ELF = "/" + EXECUTABLE
USER_NOTE = "/state/receiver-note.txt"
USER_DATA = b"Receiver-owned data added after the replacement.\n"


def inspect_install(disk, profile, package, stage, has_user_data=False):
    expected = package["manifest"]
    require(query_image(disk, profile, "info", PACKAGE_ID) == {"manifest": expected, "sha256": package["sha256"]},
            "installed package differs from the expected archive")
    files = query_image(disk, profile, "verify-installed")["files"]
    require(files == len(expected["files"]), "installed file inventory differs")
    with Disk(disk, stage, True) as backend:
        elf = backend.export(GUEST_ELF)
        digest = sha_file(elf)
        elf.unlink()
        entry = next(item for item in expected["files"] if item["path"] == EXECUTABLE)
        require(digest == entry["sha256"], "installed ELF differs from the package")
        result = {"package_sha256": package["sha256"], "revision": expected["revision"],
                  "installed_files": files, "installed_elf_sha256": digest,
                  "build_receipt_sha256": expected["build_receipt"]["sha256"]}
        if has_user_data:
            note = backend.export(USER_NOTE)
            require(note.read_bytes() == USER_DATA, "rollback differs from the receiver's data")
            result["user_note_sha256"] = sha_file(note)
            note.unlink()
    return result


def boot_app(image, disk, directory, record):
    directory.mkdir()
    guest = Guest(image, "guest", work_disk=disk, log_dir=directory)
    try:
        record["qemu_version"] = subprocess.check_output(
            [guest.command[0], "--version"], text=True).splitlines()[0]
        guest.expect(b"xos64> ", timeout=40)
        send_bytes(guest, b"run\r")
        guest.expect_supervisor(trace=True, timeout=30)
        command(guest, "demo quiet", b"demo tasks")
        record["baseline"] = resources(guest)
        display, compositor = start_graphics(guest)
        record["with_graphics"] = resources(guest)
        begin = len(guest.output)
        send_bytes(guest, f"exec-file {GUEST_ELF}\r".encode())
        guest.expect(b"QT_QUICK_EXTERNAL_FRAME", start=begin, timeout=60)
        loader = re.search(rb"\[loader\] started pid=(\d+) file=" + re.escape(GUEST_ELF.encode()) + rb"\r?\n",
                           guest.output[begin:])
        require(loader is not None, "guest did not launch the installed ELF")
        record["scanout"] = capture_external_scene(guest, directory / "scanout.ppm")
        guest.expect(b"[wait] pid=" + loader[1] + b" kind=exited code=0", start=begin)
        guest.expect_supervisor(start=begin)
        serial = guest.output[begin:]
        require(b"input-thread-joined" in serial and b"[qpa-frame]" in serial,
                "Qt input thread or display frame was missed")
        record["exit_code"] = 0
        record["after_payload"] = resources(guest)
        require(record["after_payload"] == record["with_graphics"], "Qt resources were not reclaimed")
        stop_graphics(guest, display, compositor)
        record["after_services"] = resources(guest)
        require(record["after_services"] == record["baseline"], "graphics resources were not reclaimed")
    finally:
        guest.close()
        record["serial_sha256"] = sha_file(directory / "guest_serial.log")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("system", "profile", "reference-package", "replacement-package", "output"):
        parser.add_argument("--" + field, type=Path, required=True)
    for kind in ("reference", "replacement"):
        parser.add_argument(f"--{kind}-sha256", required=True)
    args = parser.parse_args()

    system, system_digest = metadata_snapshot(args.system / "manifest.json")
    image = (args.system / "xos-install.iso").resolve(strict=True)
    image_digest = sha_file(image)
    require(image_digest == system["artifacts"][image.name]["sha256"], "system image differs from manifest")
    profile, profile_digest = metadata_snapshot(args.profile)
    require(profile.get("runtime_family") == "glibc", "expected the Qt Quick glibc profile")
    reference = verify_package(args.reference_package, profile, args.reference_sha256)
    replacement = verify_package(args.replacement_package, profile, args.replacement_sha256)
    first, second = (package["manifest"] for package in (reference, replacement))
    require(first["id"] == second["id"] == PACKAGE_ID and first["revision"] < second["revision"],
            "expected two revisions of the Qt Quick example")
    require(next(item["sha256"] for item in first["files"] if item["path"] == EXECUTABLE)
            != next(item["sha256"] for item in second["files"] if item["path"] == EXECUTABLE),
            "replacement package contains the reference ELF")
    output = args.output.resolve()
    output.mkdir(parents=True)
    report = {"status": "failed", "system_build_id": system["build_id"], "system_manifest_sha256": system_digest,
              "source_sha256": system["source_sha256"], "image_sha256": image_digest,
              "profile_sha256": profile_digest, "runner_sha256": sha_file(__file__),
              "package_id": PACKAGE_ID, "executable": GUEST_ELF, "cases": {}, "transactions": {}}
    try:
        with tempfile.TemporaryDirectory(prefix="xos_quick_receiver_") as temp:
            stage = Path(temp)
            seed = stage / "empty.img"
            installed = stage / "installed.img"
            replaced = stage / "replaced.img"
            removed = stage / "removed.img"
            recovered = stage / "recovered.img"
            create_fat32(seed, 512)

            def change(label, source, target, operation, package=None, digest=None):
                receipt = transact(source, target, profile, operation, package=package,
                                   package_id=PACKAGE_ID, expected_sha256=digest)
                del receipt["output"]
                report["transactions"][label] = receipt

            def run(label, disk, package, has_user_data=False):
                case = inspect_install(disk, profile, package, stage, has_user_data)
                case["work_disk_before_boot_sha256"] = sha_file(disk)
                report["cases"][label] = case
                boot_app(image, disk, output / label, case)

            change("install", seed, installed, "install", args.reference_package, args.reference_sha256)
            run("installed", installed, reference)
            change("replace", installed, replaced, "upgrade", args.replacement_package, args.replacement_sha256)
            run("replaced", replaced, replacement)

            note = stage / "receiver-note.txt"
            note.write_bytes(USER_DATA)
            with Disk(replaced, stage) as backend:
                if backend.info("/state") is None:
                    backend.command("mkdir", "/state")
                backend.command("import", USER_NOTE, note)
                backend.command("sync")
            change("remove_replacement", replaced, removed, "remove")
            require(query_image(removed, profile)["packages"] == [], "package survived removal")
            with Disk(removed, stage, True) as backend:
                require(backend.info(GUEST_ELF) is None, "removed application ELF is still installed")
            change("reinstall_reference", removed, recovered, "install", args.reference_package, args.reference_sha256)
            run("rolled_back", recovered, reference, True)
            require(len({case["scanout"]["sha256"] for case in report["cases"].values()}) == 1,
                    "reference, replacement and restored reference produced different scenes")
            report["status"] = "passed_subset"
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
