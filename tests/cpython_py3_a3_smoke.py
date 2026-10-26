# SPDX-License-Identifier: Apache-2.0
"""PY3 A3: package a locked pure-Python wheel through xypm and verify rollback."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

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
from xypm_format import load_json, sha_file
from xypm_image import Disk as XypmDisk

WHEEL = ROOT / ".cache/xos_seed/cpython/packages/idna-3.20-py3-none-any.whl"
LOCK = ROOT / "src/ports/cpython/idna_lock.json"
PROFILE = ROOT / "config/package/xos_x86_64_static_single_b2_v1.json"
IMAGE = ROOT / "build/iso_capacity/normal/xos.img"
DEFAULT_WORK = ROOT / ".cache/xos_seed/cpython/2b6c1342ebe6fb8c22dc"
PROBE = ROOT / "tests/fixtures/cpython_py3_a3/idna_probe.py"


def invoke(*args, success=True):
    result = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True)
    if (result.returncode == 0) != success:
        raise AssertionError(f"unexpected result {result.returncode}: {result.stdout}\n{result.stderr}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=DEFAULT_WORK)
    parser.add_argument("--image", type=Path, default=IMAGE)
    args = parser.parse_args()
    wheel = WHEEL.resolve(strict=True)
    image = args.image.resolve(strict=True)
    work = args.work.resolve(strict=True)
    package = ROOT / "build/cpython_py3_a3/idna-3.20.xpk"
    package.parent.mkdir(parents=True, exist_ok=True)
    pack = invoke(ROOT / "scripts/xypm_python_wheel.py", wheel, "--lock", LOCK, "--profile", PROFILE, "-o", package)
    package_hash = sha_file(package)
    invoke(ROOT / "scripts/xypm.py", "verify", package, "--profile", PROFILE, "--sha256", package_hash)
    stage, stage_manifest = stage_cpython(work, phase="PY3")
    report = {
        "phase": "PY3-A3-idna-offline-wheel",
        "status": "failed",
        "system_image_sha256": sha256(image),
        "stage_manifest_sha256": sha256(work / "stage_py3_manifest.json"),
        "stage_file_count": stage_manifest["file_count"],
        "wheel_sha256": sha_file(wheel),
        "package_sha256": package_hash,
        "package_id": "python_idna",
        "checks": [],
    }

    with tempfile.TemporaryDirectory(prefix="xos_cpython_py3_a3_") as folder:
        temporary = Path(folder)
        source = temporary / "source.img"
        create_fat32(source, 2048)
        install_stage(source, stage)
        transfer(source, "mkdir", "/work")
        transfer(source, "mkdir", "/work/py3a3")
        transfer(source, "import", "/work/py3a3/idna_probe.py", PROBE)
        source_hash = sha_file(source)
        installed = temporary / "installed.img"
        invoke(ROOT / "scripts/xypm.py", "install", package, "--image", source, "--output-image", installed,
               "--offline", "--profile", PROFILE, "--sha256", package_hash)
        require_unchanged = sha_file(source) == source_hash
        verified = invoke(ROOT / "scripts/xypm.py", "verify-installed", "--image", installed, "--profile", PROFILE)
        disk = installed
        guest = Guest(image, "cpython_py3_a3", work_disk=disk)
        try:
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, start=start, timeout=40)
            pump(guest, 1.0)
            baseline = resources(guest)
            text = run(guest, "python3 /work/py3a3/idna_probe.py", timeout=300)
            after = resources(guest)
            run_passed = "PY3_A3_IDNA_OK" in text and "kind=exited code=0" in text and after == baseline
            report["checks"].append({"name": "guest_import_and_idna_behavior", "passed": run_passed,
                                     "resources_before": baseline, "resources_after": after, "tail": text[-1800:]})
        finally:
            guest.close()

        removed = temporary / "removed.img"
        invoke(ROOT / "scripts/xypm.py", "remove", "python_idna", "--image", installed,
               "--output-image", removed, "--offline", "--profile", PROFILE)
        verify_removed = invoke(ROOT / "scripts/xypm.py", "list", "--image", removed, "--profile", PROFILE)
        try:
            json.loads(verify_removed.stdout)
            empty = not json.loads(verify_removed.stdout)["packages"]
        except (ValueError, KeyError):
            empty = False
        disk = XypmDisk(removed, temporary, read_only=True)
        try:
            absent_paths = [
                "usr/lib/python3.14/site-packages/idna/__init__.py",
                "usr/lib/python3.14/site-packages/idna/core.py",
                "usr/share/licenses/python_idna/LICENSE.md",
            ]
            payload_absent = all(disk.info("/" + path) is None for path in absent_paths)
        finally:
            disk.close()
        report["checks"].append({"name": "xypm_remove_rollback", "passed": empty and payload_absent,
                                 "installed_index_empty": empty, "owned_payload_absent": payload_absent})

        # A correctly pinned wheel hash is mandatory; malformed native members are rejected before packing.
        bad_hash_lock = temporary / "bad_hash_lock.json"
        bad_lock = load_json(LOCK)
        bad_lock["wheel_sha256"] = "0" * 64
        bad_hash_lock.write_text(json.dumps(bad_lock))
        bad_hash = invoke(ROOT / "scripts/xypm_python_wheel.py", wheel, "--lock", bad_hash_lock,
                          "--profile", PROFILE, "-o", temporary / "bad_hash.xpk", success=False)
        report["checks"].append({"name": "wrong_wheel_hash_rejected", "passed": "SHA256 does not match" in bad_hash.stderr})

        native = temporary / wheel.name
        with zipfile.ZipFile(wheel) as source_zip, zipfile.ZipFile(native, "w") as target_zip:
            for info in source_zip.infolist():
                target_zip.writestr(info, source_zip.read(info))
            target_zip.writestr("idna/native.so", b"not an executable")
        native_lock = temporary / "native_lock.json"
        native_lock_data = load_json(LOCK)
        native_lock_data["wheel_sha256"] = sha_file(native)
        native_lock.write_text(json.dumps(native_lock_data))
        rejected = invoke(ROOT / "scripts/xypm_python_wheel.py", native, "--lock", native_lock,
                          "--profile", PROFILE, "-o", temporary / "native.xpk", success=False)
        report["checks"].append({"name": "native_wheel_content_rejected", "passed": "native modules" in rejected.stderr})

        report["checks"].append({"name": "source_image_preserved", "passed": require_unchanged,
                                 "source_image_sha256": source_hash})
        report["status"] = "passed" if all(item["passed"] for item in report["checks"]) else "failed"
    output = ROOT / "build/cpython_py3_a3_report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    report["report_sha256"] = sha_file(output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
