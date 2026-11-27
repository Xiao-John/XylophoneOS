#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the real WebCore grant-backed CPU bitmap fixture on a normal XOS image."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes
from work_disk import transfer

MARKER = b"XOS_WEBCORE_CPU_BITMAP_GRANT_PASS readonly aliases and 16x8 red blue white"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for item in ("system", "target", "output"):
        parser.add_argument("--" + item, type=Path, required=True)
    args = parser.parse_args()
    system_file = args.system / "manifest.json"
    target_file = args.target / "target.json"
    system = json.loads(system_file.read_bytes())
    target = json.loads(target_file.read_bytes())
    image = args.system / "xos-install.iso"
    elf = args.target / "shared_memory.elf"
    fixture = ROOT / "tests/fixtures/webkit/shared_memory.cpp"
    patch = ROOT / "src/ports/webkit/page/shared_memory_xos.patch"
    if (digest(image) != system["artifacts"][image.name]["sha256"] or digest(elf) != target["elf_sha256"]
            or digest(fixture) != target["fixture_sha256"] or digest(patch) != target["patch_sha256"]
            or any(digest(ROOT / name) != value for name, value in system["sources"].items())):
        raise ValueError("Guest inputs differ from their build receipts")

    args.output.mkdir(parents=True)
    report = {"status": "failed", "build_id": system["build_id"], "iso_sha256": digest(image),
              "system_manifest_sha256": digest(system_file), "target_manifest_sha256": digest(target_file),
              "elf_sha256": digest(elf), "runs": [], "runner_sha256": digest(Path(__file__))}
    try:
        with tempfile.TemporaryDirectory(prefix="xos_webcore_shared_memory_") as directory:
            stage = Path(directory)
            disk = stage / "work.img"
            recovered = stage / elf.name
            guest_path = "/shared_memory.elf"
            create_fat32(disk, 512)
            transfer(disk, "import", guest_path, elf)
            transfer(disk, "export", guest_path, recovered)
            report["fat_readback_sha256"] = digest(recovered)
            if report["fat_readback_sha256"] != report["elf_sha256"]:
                raise ValueError("Installed probe differs from the linked ELF")
            guest = Guest(image, "guest", work_disk=disk, log_dir=args.output)
            try:
                report["qemu"] = subprocess.check_output([guest.command[0], "--version"], text=True).splitlines()[0]
                guest.expect(b"xos64> ", timeout=40)
                send_bytes(guest, b"run\r")
                guest.expect_supervisor(trace=True, timeout=40)
                command(guest, "demo quiet", b"demo tasks")
                report["resources_before"] = resources(guest)
                for _ in range(3):
                    serial = command(guest, "exec-file " + guest_path, b"[wait] pid=", timeout=90)
                    result = re.findall(rb"\[wait\] pid=\d+ kind=exited code=(\d+)", serial)
                    after = resources(guest)
                    report["runs"].append({"marker_count": serial.count(MARKER), "exits": [int(code) for code in result],
                                           "resources_after": after})
                    if result != [b"0"] or serial.count(MARKER) != 1 or after != report["resources_before"]:
                        raise AssertionError(f"CPU shareable bitmap test failed: {serial[-800:]!r}")
                report["status"] = "passed_subset"
            finally:
                guest.close()
                report["serial_sha256"] = digest(args.output / "guest_serial.log")
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
