#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run authenticated two-process WebCore bitmap loans on an ordinary XOS image."""

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

MARKER = b"XOS_WEBCORE_BITMAP_TRANSFER_PASS RO RW peer binding, release and both exit orders"
REQUIRED_PATCHES = {"software_context.patch", "software_buffers.patch", "software_graph.patch",
                    "shared_memory_xos.patch", "shared_memory_transfer_xos.patch"}
CASES = re.compile(rb"XOS_WEBCORE_BITMAP_TRANSFER_CASE mode=(\d+) parent=(\d+) child=(\d+)")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def exits(serial):
    return [int(code) for code in re.findall(rb"\[wait\] pid=\d+ kind=exited code=(\d+)", serial)]


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
    elf = args.target / "shared_memory_transfer.elf"
    fixture = ROOT / "tests/fixtures/webkit/shared_memory_transfer.cpp"
    patches = ROOT / "src/ports/webkit/page"
    if (digest(image) != system["artifacts"][image.name]["sha256"] or digest(elf) != target["elf_sha256"]
            or digest(fixture) != target["fixture_sha256"]
            or set(target["patches"]) != REQUIRED_PATCHES
            or any(digest(patches / name) != value for name, value in target["patches"].items())
            or any(digest(ROOT / name) != value for name, value in system["sources"].items())):
        raise ValueError("Guest inputs differ from their build receipts")

    args.output.mkdir(parents=True)
    report = {"status": "failed", "build_id": system["build_id"], "iso_sha256": digest(image),
              "system_manifest_sha256": digest(system_file), "target_manifest_sha256": digest(target_file),
              "elf_sha256": digest(elf), "runs": [], "runner_sha256": digest(Path(__file__))}
    try:
        with tempfile.TemporaryDirectory(prefix="xos_webcore_bitmap_transfer_") as directory:
            stage = Path(directory)
            disk = stage / "work.img"
            recovered = stage / elf.name
            guest_path = "/shared_memory_transfer.elf"
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
                denied = command(guest, "exec-file " + guest_path, b"[wait] pid=", timeout=90)
                report["restricted_launch"] = {
                    "exits": exits(denied), "spawn_denied": b"XOS_WEBCORE_BITMAP_TRANSFER_SPAWN_ERROR 1" in denied,
                    "cases": len(CASES.findall(denied)), "resources_after": resources(guest),
                }
                if report["restricted_launch"] != {
                    "exits": [1], "spawn_denied": True, "cases": 0, "resources_after": report["resources_before"],
                }:
                    raise AssertionError(f"Restricted fixture acquired process-create authority: {denied[-800:]!r}")
                for _ in range(3):
                    serial = command(guest, guest_path, b"[wait] pid=", timeout=90)
                    result = exits(serial)
                    cases = [{"mode": int(mode), "parent": int(parent), "child": int(child)}
                             for mode, parent, child in CASES.findall(serial)]
                    after = resources(guest)
                    report["runs"].append({"marker_count": serial.count(MARKER), "exits": result,
                                           "resources_after": after, "cases": cases})
                    if (result != [0] or serial.count(MARKER) != 1 or after != report["resources_before"]
                            or [case["mode"] for case in cases] != [1, 2, 3, 4]
                            or len({case["parent"] for case in cases}) != 1
                            or len({case["child"] for case in cases}) != 4
                            or any(case["child"] == case["parent"] for case in cases)):
                        raise AssertionError(f"CPU bitmap loan test failed: {serial[-800:]!r}")
                report["status"] = "passed_subset"
            finally:
                guest.close()
                report["serial_sha256"] = digest(args.output / "guest_serial.log")
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
