# SPDX-License-Identifier: Apache-2.0
"""PY3 A1: exercise the selected CPython standard-library closure on XOS."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from cpython_py0b_smoke import run
from make_work_disk import create_fat32
from process_smoke import resources
from stage_cpython import sha256, stage_cpython
from task_smoke import pump, send_bytes
from work_disk import transfer


FIXTURE = ROOT / "tests/fixtures/cpython_py3_a1/stdlib_probe.py"
DEFAULT_WORK = ROOT / ".cache/xos_seed/cpython/c69e0fbf7772c775ab3e"
DEFAULT_IMAGE = ROOT / "build/iso_capacity/normal/xos.img"


def install_stage(disk, stage):
    directories = sorted(
        (path for path in stage.rglob("*") if path.is_dir()),
        key=lambda path: (len(path.relative_to(stage).parts), str(path)),
    )
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
    stage, stage_manifest = stage_cpython(work)
    report = {
        "phase": "PY3-A1",
        "status": "failed",
        "xos_image_sha256": sha256(image),
        "cpython_fingerprint": stage_manifest["fingerprint"],
        "stage_manifest_sha256": sha256(work / "stage_py1_manifest.json"),
        "checks": [],
    }

    with tempfile.TemporaryDirectory(prefix="xos_cpython_py3_a1_") as folder:
        disk = Path(folder) / "work.img"
        create_fat32(disk, 2048)
        install_stage(disk, stage)
        transfer(disk, "mkdir", "/work")
        transfer(disk, "mkdir", "/work/py3a1")
        transfer(disk, "import", "/work/py3a1/stdlib_probe.py", FIXTURE)

        guest = Guest(image, "cpython_py3_a1", work_disk=disk)
        try:
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, start=start, timeout=40)
            pump(guest, 1.0)
            baseline = resources(guest)
            text = run(guest, "python3 /work/py3a1/stdlib_probe.py", timeout=240)
            after = resources(guest)
            reclaimed = [
                int(value) for value in re.findall(
                    r"event=reclaimed pid=\d+ pages=(\d+)", text
                )
            ]
            passed = (
                "PY3_A1_OK" in text
                and "kind=exited code=0" in text
                and after == baseline
                and bool(reclaimed)
            )
            statistics_blocked = "PY3_A1_STATISTICS blocked_without_system_entropy:" in text
            if statistics_blocked:
                report["known_blockers"] = [
                    "statistics imports random, whose default seed requires unavailable system entropy"
                ]
            report["checks"].append({
                "name": "selected_stdlib_known_vectors_and_operations",
                "passed": passed,
                "statistics": "blocked_by_missing_system_entropy" if statistics_blocked else "passed",
                "resources_before": baseline,
                "resources_after": after,
                "reclaimed_pages": max(reclaimed, default=0),
                "tail": text[-1800:],
            })
            report["status"] = "passed" if passed else "failed"
        finally:
            guest.close()

    output = ROOT / "build/cpython_py3_a1_report.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
