# SPDX-License-Identifier: Apache-2.0
"""PY3 B4 guest gate for static bz2, lzma and zstd modules."""

import argparse
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


FIXTURE = ROOT / "tests/fixtures/cpython_py3_b4/compression_probe.py"
DEFAULT_IMAGE = ROOT / "build/iso_capacity/normal/xos.img"
DEFAULT_REPORT = ROOT / ".cache/xos_seed/cpython/compression/guest_report.json"


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
    parser.add_argument("--work", type=Path, required=True,
                        help="the matching CPython PY3 work directory")
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--compression-report", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    work = args.work.resolve(strict=True)
    image = args.image.resolve(strict=True)
    compression_path = args.compression_report.resolve(strict=True)
    compression_report = json.loads(compression_path.read_text())
    if compression_report.get("status") != "built":
        parser.error("compression receipt is not a successful build")
    stage, stage_manifest = stage_cpython(work, phase="PY3")
    report = {
        "phase": "PY3-B4-compression",
        "status": "failed",
        "xos_image_sha256": sha256(image),
        "cpython_fingerprint": stage_manifest["fingerprint"],
        "stage_manifest_sha256": sha256(work / f"{stage.name}_manifest.json"),
        "stage_file_count": stage_manifest["file_count"],
        "compression_fingerprint": compression_report["fingerprint"],
        "components": {
            name: {
                "version": value["version"],
                "source_archive_sha256": value["source_archive_sha256"],
                "license_id": value["license_id"],
                "license_sha256": value["license_sha256"],
                "library_sha256": value["library_sha256"],
            }
            for name, value in compression_report["components"].items()
        },
        "checks": [],
    }
    with tempfile.TemporaryDirectory(prefix="xos_cpython_py3_b4_") as folder:
        disk = Path(folder) / "work.img"
        create_fat32(disk, 2048)
        install_stage(disk, stage)
        transfer(disk, "mkdir", "/work")
        transfer(disk, "mkdir", "/work/py3b4")
        transfer(disk, "import", "/work/py3b4/compression_probe.py", FIXTURE)

        guest = Guest(image, "cpython_py3_b4", work_disk=disk)
        try:
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, start=start, timeout=40)
            pump(guest, 1.0)
            baseline = resources(guest)
            output = run(guest, "python3 /work/py3b4/compression_probe.py", timeout=300)
            after = resources(guest)
            reclaimed = [
                int(value) for value in re.findall(
                    r"event=reclaimed pid=\d+ pages=(\d+)", output
                )
            ]
            for module in ("BZ2", "LZMA", "ZSTD"):
                report["checks"].append({
                    "name": module.lower() + "_roundtrip_stream_corruption_truncation_and_bounds",
                    "passed": f"PY3_B4_{module}_OK" in output,
                })
            resources_ok = after == baseline and bool(reclaimed)
            report["checks"].append({
                "name": "python_process_exit_and_resource_reclaim",
                "passed": "PY3_B4_OK" in output and "kind=exited code=0" in output
                          and resources_ok,
                "resources_before": baseline,
                "resources_after": after,
                "reclaimed_pages": max(reclaimed, default=0),
            })
            report["output_tail"] = output[-3000:]
            report["status"] = "passed" if all(check["passed"] for check in report["checks"]) else "failed"
        finally:
            guest.close()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
