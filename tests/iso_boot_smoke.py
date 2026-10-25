# SPDX-License-Identifier: Apache-2.0
"""Boot the El Torito ISO and reach the supervisor shell."""

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
    parser.add_argument("--report", type=Path, default=ROOT / "build/iso_boot_report.json")
    args = parser.parse_args()
    system = json.loads((ROOT / "build/manifest.json").read_text())
    report = {"gate": "ISO boot", "build_id": system["build_id"],
              "xos_iso_sha256": sha256(ROOT / "build/xos.iso"), "checks": [],
              "status": "failed"}
    with tempfile.TemporaryDirectory(prefix="xos_iso_") as folder:
        disk = Path(folder) / "work.img"
        create_fat32(disk, 512)
        guest = Guest(ROOT / "build/xos.iso", "iso_boot", work_disk=disk, iso=True)
        try:
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(start=start, timeout=40)
            pump(guest, 0.5)
            report["checks"].append({"name": "boot-to-shell", "passed": True})
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
