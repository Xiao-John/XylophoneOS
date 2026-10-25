# SPDX-License-Identifier: Apache-2.0
"""A2: boot a kernel read from the ISO9660 KERNEL.BIN file."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from make_work_disk import create_fat32
from task_smoke import pump, send_bytes


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "build/iso_file_kernel_report.json")
    args = parser.parse_args()
    image = ROOT / "build/xos-install.iso"
    system = json.loads((ROOT / "build/manifest.json").read_text())
    report = {"gate": "A2 file-backed kernel", "build_id": system["build_id"],
              "iso_sha256": sha256(image), "checks": [], "status": "failed"}
    with tempfile.TemporaryDirectory(prefix="xos_iso_file_") as folder:
        disk = Path(folder) / "work.img"
        create_fat32(disk, 512)
        guest = Guest(image, "iso_file_kernel", iso=True, work_disk=disk)
        try:
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(start=start, timeout=60)
            pump(guest, 0.5)
            report["checks"].append({"name": "kernel-from-file", "passed": True})
            begin = len(guest.output)
            send_bytes(guest, b"type hello\r")
            guest.expect(b"hello", start=begin, timeout=20)
            guest.expect_any((b"xsh> ", b"sup> "), start=begin, timeout=20)
            report["checks"].append({"name": "files-service", "passed": True})
        finally:
            guest.close()
    report["status"] = "passed" if all(c["passed"] for c in report["checks"]) else "failed"
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
