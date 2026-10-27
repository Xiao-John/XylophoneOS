# SPDX-License-Identifier: Apache-2.0
"""PY3 B3: SQLite database, busy/constraint errors, sync and guest reboot."""

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
from process_smoke import command, resources
from stage_cpython import sha256, stage_cpython
from task_smoke import pump, send_bytes
from work_disk import transfer


FIXTURE = ROOT / "tests/fixtures/cpython_py3_b3/sqlite_probe.py"
DEFAULT_IMAGE = ROOT / "build/xos.img"
OUTPUT_DIR = ROOT / ".cache/xos_seed/cpython/sqlite"


def boot(image, disk, name):
    guest = Guest(image, name, work_disk=disk)
    guest.expect(b"xos64> ", timeout=30)
    start = len(guest.output)
    send_bytes(guest, b"run\r")
    guest.expect_supervisor(trace=True, start=start, timeout=40)
    pump(guest, 1.0)
    return guest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True,
                        help="the matching CPython PY3 work directory")
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    args = parser.parse_args()
    work = args.work.resolve(strict=True)
    image = args.image.resolve(strict=True)
    stage, stage_manifest = stage_cpython(work, phase="PY3")
    build_report = json.loads((work / "py0a_report.json").read_text())
    receipt_path = (Path(build_report["sqlite_prefix"]).parent / "receipt.json"
                    if build_report.get("sqlite_prefix") else None)
    receipt = json.loads(receipt_path.read_text()) if receipt_path else None
    report = {
        "phase": "PY3-B3-sqlite",
        "status": "not_run",
        "xos_image_sha256": sha256(image),
        "cpython_fingerprint": stage_manifest["fingerprint"],
        "stage_manifest_sha256": sha256(work / f"{stage.name}_manifest.json"),
        "stage_file_count": stage_manifest["file_count"],
        "cpython_profile": build_report.get("profile"),
        "sqlite_receipt_fingerprint": receipt.get("fingerprint") if receipt else None,
        "sqlite_library_sha256": receipt.get("library_sha256") if receipt else None,
        "checks": [],
    }
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix="xos_cpython_py3_b3_") as folder:
            temporary = Path(folder)
            private_image = temporary / "xos.img"
            disk = temporary / "work.img"
            shutil.copyfile(image, private_image)
            create_fat32(disk, 2048)
            install_stage(disk, stage)
            transfer(disk, "mkdir", "/work")
            transfer(disk, "mkdir", "/work/py3b3")
            transfer(disk, "import", "/work/py3b3/sqlite_probe.py", FIXTURE)

            guest = boot(private_image, disk, "cpython_py3_b3_first")
            baseline = resources(guest)
            first_text = run(guest, "python3 /work/py3b3/sqlite_probe.py first", timeout=240)
            module_available = (
                "No module named 'sqlite3'" not in first_text
                and "No module named _sqlite3" not in first_text
            )
            first_passed = "PY3_B3_FIRST_OK" in first_text and "kind=exited code=0" in first_text
            report["checks"].append({
                "name": "create_transactions_unique_busy_corrupt",
                "passed": first_passed,
                "module_available": module_available,
                "resources_before": baseline,
                "resources_after": resources(guest),
                "tail": first_text[-2200:],
            })
            if not module_available:
                report["status"] = "blocked_missing_sqlite_integration"
            elif not first_passed:
                report["status"] = "failed"
            else:
                command(guest, "sync", b"[files] sync=ok", timeout=30)
                guest.close()
                guest = boot(private_image, disk, "cpython_py3_b3_reboot")
                reboot_baseline = resources(guest)
                reopen_text = run(guest, "python3 /work/py3b3/sqlite_probe.py reopen", timeout=180)
                reopen_passed = "PY3_B3_REOPEN_OK" in reopen_text and "kind=exited code=0" in reopen_text
                report["checks"].append({
                    "name": "sync_reboot_reopen_integrity",
                    "passed": reopen_passed,
                    "resources_before": reboot_baseline,
                    "resources_after": resources(guest),
                    "tail": reopen_text[-1600:],
                })
                report["status"] = "passed" if reopen_passed else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        if guest is not None:
            guest.close()
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output = OUTPUT_DIR / f"guest_report_{stage_manifest['fingerprint']}.json"
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
