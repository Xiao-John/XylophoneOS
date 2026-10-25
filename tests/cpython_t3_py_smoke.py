# SPDX-License-Identifier: Apache-2.0
"""T3-PY: exercise CPython's real pthread backend inside an XOS guest."""

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from cpython_py0b_smoke import run
from cpython_py1_smoke import install_stage
from make_work_disk import create_fat32
from process_smoke import resources
from stage_cpython import sha256, stage_cpython
from task_smoke import pump, send_bytes
from work_disk import transfer


FIXTURES = ROOT / "tests/fixtures/cpython_t3_py"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--image", type=Path, default=ROOT / "build/xos.img")
    args = parser.parse_args()
    work = args.work.resolve(strict=True)
    stage, stage_manifest = stage_cpython(work)
    build_report = json.loads((work / "py0a_report.json").read_text())
    if build_report.get("profile") != "py_t3_static_gil_pthread":
        parser.error("the selected interpreter is not the T3-PY pthread profile")
    report = {
        "phase": "T3-PY",
        "status": "failed",
        "build_id": json.loads((ROOT / "build/manifest.json").read_text())["build_id"],
        "xos_image_sha256": sha256(args.image),
        "cpython_fingerprint": stage_manifest["fingerprint"],
        "cpython_profile": build_report["profile"],
        "sdk_manifest_sha256": build_report["sdk_manifest_sha256"],
        "stage_manifest_sha256": sha256(work / "stage_py1_manifest.json"),
        "stage_file_count": stage_manifest["file_count"],
        "checks": [],
    }
    guest = None
    output_path = ROOT / "build/cpython_t3_py_report.json"
    try:
        with tempfile.TemporaryDirectory(prefix="xos_cpython_t3_py_") as folder:
            temporary = Path(folder)
            image = temporary / "xos.img"
            disk = temporary / "work.img"
            shutil.copyfile(args.image, image)
            create_fat32(disk, 2048)
            install_stage(disk, stage)
            for guest_path in ("/work", "/work/t3_py"):
                transfer(disk, "mkdir", guest_path)
            for fixture in sorted(FIXTURES.glob("*.py")):
                transfer(disk, "import", f"/work/t3_py/{fixture.name}", fixture)
            payload = temporary / "io_payload.bin"
            payload.write_bytes(b"XOS!" + bytes(256 * 1024 - 8) + b"T3PY")
            transfer(disk, "import", "/work/t3_py/io_payload.bin", payload)

            guest = Guest(image, "cpython_t3_py", work_disk=disk)
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, start=start, timeout=40)
            pump(guest, 1.0)
            baseline = resources(guest)
            report["resources_before"] = baseline

            def check(name, fixture, expected, *, timeout=180):
                text = run(guest, f"python3 /work/t3_py/{fixture}", timeout=timeout)
                after = resources(guest)
                passed = (
                    expected in text
                    and "kind=exited code=0" in text
                    and "AssertionError" not in text
                    and after == baseline
                )
                report["checks"].append({
                    "name": name,
                    "fixture": fixture,
                    "expected": expected,
                    "resources_after": after,
                    "passed": passed,
                    "tail": text[-1400:],
                })
                return passed

            results = [
                check(
                    "threading_lock_rlock_condition_event_queue",
                    "threading_core.py",
                    "T3_PY_CORE_OK Lock RLock Condition Event Queue",
                ),
                check(
                    "background_thread_progress_during_main_file_io",
                    "blocking_io.py",
                    "T3_PY_BLOCKING_IO_OK",
                ),
                check(
                    "worker_exception_hook_and_join",
                    "worker_exception.py",
                    "T3_PY_EXCEPTION_OK",
                ),
                check(
                    "daemon_thread_does_not_block_process_exit",
                    "daemon_exit.py",
                    "T3_PY_DAEMON_EXIT_OK",
                ),
                check(
                    "interpreter_waits_for_non_daemon_thread",
                    "non_daemon_shutdown.py",
                    "T3_PY_NON_DAEMON_FINISHED",
                ),
            ]
            report["status"] = "passed" if all(results) else "failed"
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        if guest is not None:
            guest.close()
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
