# SPDX-License-Identifier: Apache-2.0
"""PY3 B2: verify PC RTC wall time and CPython timezone handling in QEMU."""

import argparse
import json
from pathlib import Path
import re
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from cpython_py0b_smoke import run
from make_work_disk import create_fat32
from process_smoke import resources
from stage_cpython import sha256, stage_cpython
from task_smoke import pump, send_bytes
from work_disk import transfer

DEFAULT_WORK = ROOT / ".cache/xos_seed/cpython/0739062ab231f71676c8"
DEFAULT_IMAGE = ROOT / "build/cpython_py3_b2/system/xos.img"
FIXTURE = ROOT / "tests/fixtures/cpython_py3_b2/timezone_probe.py"


def install_stage(disk, stage):
    directories = sorted((path for path in stage.rglob("*") if path.is_dir()),
                         key=lambda path: (len(path.relative_to(stage).parts), str(path)))
    for path in directories:
        transfer(disk, "mkdir", "/" + path.relative_to(stage).as_posix())
    for path in sorted(stage.rglob("*")):
        if path.is_file():
            transfer(disk, "import", "/" + path.relative_to(stage).as_posix(), path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=DEFAULT_WORK)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    args = parser.parse_args()
    work = args.work.resolve(strict=True)
    image = args.image.resolve(strict=True)
    stage, stage_manifest = stage_cpython(work, phase="PY3")
    image_manifest = json.loads((image.parent / "manifest.json").read_text())
    qemu = __import__("run_qemu").qemu_command(image)[0]
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix="xos_cpython_py3_b2_") as folder:
            disk = Path(folder) / "work.img"
            create_fat32(disk, 2048)
            install_stage(disk, stage)
            transfer(disk, "mkdir", "/work")
            transfer(disk, "mkdir", "/work/py3b2")
            transfer(disk, "import", "/work/py3b2/timezone_probe.py", FIXTURE)
            guest = Guest(image, "py3_b2_realtime_tz", cpu="qemu64,+rdrand", work_disk=disk)
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, start=start, timeout=40)
            pump(guest, 1.0)
            baseline = resources(guest)
            host_start_ns = time.time_ns()
            output = run(guest, "python3 /work/py3b2/timezone_probe.py", timeout=180)
            host_end_ns = time.time_ns()
            host_match = re.search(r"wall_ns=(\d+)", output)
            if ("PY3_B2_REALTIME_TZDATA_OK" not in output or
                    "kind=exited code=0" not in output or not host_match):
                raise AssertionError(f"B2 guest failed\n{output[-2000:]}")
            wall_ns = int(host_match.group(1))
            if not host_start_ns - 30_000_000_000 <= wall_ns <= host_end_ns + 30_000_000_000:
                raise AssertionError(f"guest wall time not near host UTC: {wall_ns}")
            after = resources(guest)
            if after != baseline:
                raise AssertionError(f"guest resources changed: {baseline} -> {after}")
            report = {
                "phase": "PY3-B2-realtime-timezone",
                "status": "passed",
                "system_build_id": image_manifest["build_id"],
                "xos_image_sha256": sha256(image),
                "cpython_fingerprint": stage_manifest["fingerprint"],
                "cpython_sha256": sha256(work / "target_build/python.exe"),
                "tzdata": stage_manifest["timezone_data"],
                "qemu_version": __import__("subprocess").check_output([qemu, "--version"], text=True).splitlines()[0],
                "guest_wall_ns": wall_ns,
                "host_wall_window_ns": [host_start_ns, host_end_ns],
                "resources_before": baseline,
                "resources_after": after,
                "tail": output[-1200:],
            }
            report_path = ROOT / "build/cpython_py3_b2_report.json"
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
            print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        if guest is not None:
            guest.close()


if __name__ == "__main__":
    main()
