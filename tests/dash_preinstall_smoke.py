# SPDX-License-Identifier: Apache-2.0
"""Verify a newly created work disk has a runnable /usr/bin/dash."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from install_dash import install, latest_manifest
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
    parser.add_argument("--report", type=Path,
                        default=ROOT / "build/dash_preinstall_report.json")
    args = parser.parse_args()
    system = json.loads((ROOT / "build/manifest.json").read_text())
    report = {"gate": "dash preinstall", "build_id": system["build_id"],
              "xos_image_sha256": sha256(ROOT / "build/xos.img"),
              "checks": [], "status": "failed"}
    with tempfile.TemporaryDirectory(prefix="xos_dash_preinstall_") as folder:
        disk = Path(folder) / "work.img"
        create_fat32(disk, 512)
        installed = install(disk, latest_manifest())
        report["dash"] = installed
        guest = Guest(ROOT / "build/xos.img", "dash_preinstall", work_disk=disk)
        try:
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(start=start, timeout=40)
            pump(guest, 0.5)
            send_bytes(guest, b"demo quiet\r")
            guest.expect(b"demo tasks", start=len(guest.output) - 64, timeout=20)
            pump(guest, 0.4)
            commands = [(b"type dash\r", b"dash -> /usr/bin/dash"),
                        (b"dash -i\r", b"$ "),
                        (b"echo PREINSTALLED_DASH\r", b"PREINSTALLED_DASH"),
                        (b"exit\r", b"xsh> ")]
            for command, expected in commands:
                begin = len(guest.output)
                send_bytes(guest, command)
                guest.expect(expected, start=begin, timeout=30)
                pump(guest, 0.2)
                report["checks"].append({"command": command.decode().strip(),
                                         "passed": True})
        finally:
            guest.close()
    report["status"] = "passed" if all(c["passed"] for c in report["checks"]) else "failed"
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
