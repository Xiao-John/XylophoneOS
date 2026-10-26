# SPDX-License-Identifier: Apache-2.0
"""PY3 A2: exercise static zlib, gzip, deflate ZIP and corrupt inputs on XOS."""

import argparse
import json
from pathlib import Path
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


FIXTURE = ROOT / "tests/fixtures/cpython_py3_a2/zlib_probe.py"
DEFAULT_WORK = ROOT / ".cache/xos_seed/cpython/2b6c1342ebe6fb8c22dc"
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
    stage, stage_manifest = stage_cpython(work, phase="PY3")
    build_report = json.loads((work / "py0a_report.json").read_text())
    zlib_report = json.loads((Path(build_report["zlib_prefix"]).parent / "report.json").read_text())
    report = {
        "phase": "PY3-A2-zlib",
        "status": "failed",
        "xos_image_sha256": sha256(image),
        "cpython_fingerprint": stage_manifest["fingerprint"],
        "stage_manifest_sha256": sha256(work / "stage_py3_manifest.json"),
        "stage_file_count": stage_manifest["file_count"],
        "zlib_license_sha256": sha256(stage / "usr/share/licenses/zlib/LICENSE"),
        "zlib_fingerprint": zlib_report["fingerprint"],
        "zlib_version": zlib_report["version"],
        "zlib_library_sha256": zlib_report["libz_sha256"],
        "checks": [],
    }

    with tempfile.TemporaryDirectory(prefix="xos_cpython_py3_a2_") as folder:
        disk = Path(folder) / "work.img"
        create_fat32(disk, 2048)
        install_stage(disk, stage)
        transfer(disk, "mkdir", "/work")
        transfer(disk, "mkdir", "/work/py3a2")
        transfer(disk, "import", "/work/py3a2/zlib_probe.py", FIXTURE)

        guest = Guest(image, "cpython_py3_a2", work_disk=disk)
        try:
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, start=start, timeout=40)
            pump(guest, 1.0)
            baseline = resources(guest)
            text = run(guest, "python3 /work/py3a2/zlib_probe.py", timeout=300)
            after = resources(guest)
            reclaimed = [
                int(value) for value in __import__("re").findall(
                    r"event=reclaimed pid=\d+ pages=(\d+)", text
                )
            ]
            passed = (
                "PY3_A2_OK" in text
                and "kind=exited code=0" in text
                and after == baseline
                and bool(reclaimed)
            )
            report["checks"].append({
                "name": "zlib_gzip_zipimport_and_malformed_data",
                "passed": passed,
                "resources_before": baseline,
                "resources_after": after,
                "reclaimed_pages": max(reclaimed, default=0),
                "tail": text[-2000:],
            })
            report["status"] = "passed" if passed else "failed"
        finally:
            guest.close()

    output = ROOT / "build/cpython_py3_a2_report.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
