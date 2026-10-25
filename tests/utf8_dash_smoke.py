# SPDX-License-Identifier: Apache-2.0
"""U1: dash console adapter accepts, edits and rejects UTF-8 lines."""

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
from work_disk import transfer

PROMPTS = (b"xsh> ", b"sup> ")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dash", type=Path, required=True)
    parser.add_argument("--image", type=Path, default=ROOT / "build/xos.img")
    parser.add_argument("--report", type=Path,
                        default=ROOT / "build/utf8_dash_report.json")
    args = parser.parse_args()
    system = json.loads((ROOT / "build/manifest.json").read_text())
    report = {
        "gate": "U1 dash UTF-8 console",
        "build_id": system["build_id"],
        "xos_image_sha256": sha256(args.image),
        "dash_sha256": sha256(args.dash),
        "checks": [],
        "status": "failed",
    }
    with tempfile.TemporaryDirectory(prefix="xos_utf8_dash_") as folder:
        disk = Path(folder) / "dash.img"
        create_fat32(disk, 2048)
        for path in ("/usr", "/usr/bin", "/tmp"):
            transfer(disk, "mkdir", path)
        transfer(disk, "import", "/usr/bin/dash", args.dash)
        guest = Guest(args.image, "utf8_dash", work_disk=disk)
        try:
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(start=start, timeout=40)
            pump(guest, 0.5)
            send_bytes(guest, b"demo quiet\r")
            guest.expect(b"demo tasks", start=len(guest.output) - 64, timeout=20)
            pump(guest, 0.5)

            def send(line, expected, timeout=30):
                begin = len(guest.output)
                send_bytes(guest, line)
                guest.expect(expected, start=begin, timeout=timeout)
                pump(guest, 0.2)
                return bytes(guest.output[begin:])

            def check(name, passed, **extra):
                report["checks"].append({"name": name, "passed": passed, **extra})

            begin = len(guest.output)
            send_bytes(guest, b"dash\r")
            guest.expect(b"$ ", start=begin, timeout=40)
            pump(guest, 0.3)

            send(b"echo \xe4\xbd\xa0\xe5\xa5\xbd\r", b"\xe4\xbd\xa0\xe5\xa5\xbd")
            check("echo", True)

            text = send(b"echo ab\xc3\xa9\x7fc\r", b"abc")
            check("backspace", b"abc" in text and b"\x08 \x08" in text)

            send(b"\xff\r", b"dash: invalid UTF-8 input")
            check("invalid-sequence", True)

            begin = len(guest.output)
            send_bytes(guest, b"exit\r")
            guest.expect_any(PROMPTS, start=begin, timeout=30)
            check("exit", True)
        finally:
            guest.close()
    report["status"] = "passed" if all(c["passed"] for c in report["checks"]) else "failed"
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
