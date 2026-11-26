#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the static XOS JavaScriptCore shell with an ordinary guest script."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import pump, send_bytes
from work_disk import transfer


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("image", "payload", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-resources", type=int, nargs=3, required=True,
                        metavar=("PAGES", "TASKS", "COMPLETIONS"),
                        help="baseline for the selected ordinary system after demo tasks stop")
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    script = ROOT / "tests/fixtures/webkit/jsc_smoke.js"
    report = {"status": "failed", "image_sha256": sha(args.image),
              "runner_sha256": sha(Path(__file__)), "expected_resources": args.expected_resources,
              "jsc_sha256": sha(args.payload), "script_sha256": sha(script)}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix="xos_jsc_") as temporary:
            directory = Path(temporary)
            disk = directory / "work.img"
            image = directory / "boot.iso"
            shutil.copyfile(args.image, image)
            create_fat32(disk, 512)
            transfer(disk, "mkdir", "/js")
            transfer(disk, "import", "/js/jsc", args.payload)
            transfer(disk, "import", "/js/smoke.js", script)
            guest = Guest(image, "jsc_static_guest", work_disk=disk, log_dir=args.report.parent)
            report["qemu_version"] = subprocess.check_output(
                [guest.command[0], "--version"], text=True).splitlines()[0]
            guest.expect(b"xos64> ", timeout=30)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, timeout=30)
            command(guest, "demo quiet", b"demo tasks")
            pump(guest, 1.5)
            report["resources_before"] = resources(guest)
            if report["resources_before"] != tuple(args.expected_resources):
                raise AssertionError(f"guest baseline differs from the expected {args.expected_resources}")
            output = command(guest, "exec-file /js/jsc /js/smoke.js", b"kind=", timeout=240)
            status = re.findall(rb"\[wait\] pid=\d+ kind=(\w+) code=(-?\d+)", output)
            report["wait_status"] = [[kind.decode(), int(code)] for kind, code in status]
            report["resources_after"] = resources(guest)
            if status != [(b"exited", b"0")]:
                raise AssertionError(output[-6000:])
            if output.replace(b"\r", b"").splitlines().count(b"CLARKE_JSC_LLINT_PASS 6,15,36") != 1:
                raise AssertionError(output[-6000:])
            report["script_output"] = "CLARKE_JSC_LLINT_PASS 6,15,36"
            if report["resources_before"] != report["resources_after"]:
                raise AssertionError("jsc changed the guest resource baseline")
            report["status"] = "passed"
    finally:
        if guest:
            guest.close()
            args.report.with_suffix(".serial.log").write_bytes(guest.output)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
