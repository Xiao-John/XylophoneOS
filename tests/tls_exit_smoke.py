# SPDX-License-Identifier: Apache-2.0
"""Verify TLS destructors run before newlib global exit handlers in XOS."""

import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from e08_storage_smoke import boot
from make_work_disk import create_fat32
from process_smoke import command, resources
from work_disk import transfer


ORDER = (
    b"[tls_exit] tls_b_dtor",
    b"[tls_exit] tls_late_dtor",
    b"[tls_exit] tls_a_dtor",
    b"[tls_exit] atexit_handler",
    b"[tls_exit] global_dtor",
    b"[tls_exit] fini",
)


def verify_path(guest, args, baseline):
    output = command(guest, "exec-file /bin/tls_exit_probe.elf" + args,
                     b"kind=exited code=", timeout=45)
    if b"kind=exited code=0" not in output:
        raise AssertionError(f"exit path returned nonzero: {output[-1800:]!r}")
    if b"[tls_exit] FAIL" in output:
        raise AssertionError(f"probe reported a failure: {output[-1800:]!r}")
    counts = [output.count(marker) for marker in ORDER]
    if any(count != 1 for count in counts):
        raise AssertionError(f"lifecycle marker counts are not exactly one: {counts}; {output[-1800:]!r}")
    positions = [output.find(marker) for marker in ORDER]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise AssertionError(f"TLS/global cleanup order is wrong: {positions}; {output[-1800:]!r}")
    if args == " exit" and b"[tls_exit] explicit_exit" not in output:
        raise AssertionError("explicit exit path did not reach exit() from main")
    if args == "" and b"[tls_exit] main_return" not in output:
        raise AssertionError("main-return path did not reach exit() after main returned")
    current = resources(guest)
    if current != baseline:
        raise AssertionError(f"exit path leaked resources: {current} != {baseline}")
    return {"output_sha256": hashlib.sha256(output).hexdigest(),
            "resources": current,
            "markers": [marker.decode("ascii") for marker in ORDER]}


def main():
    build = ROOT / "build"
    manifest = json.loads((build / "manifest.json").read_text(encoding="utf-8"))
    image = build / "user_tls_exit_probe.image.elf"
    if not image.is_file():
        raise SystemExit("Missing build/user_tls_exit_probe.image.elf; integrate and build the probe first")
    sources = ("src/user/programs/tls_exit_probe.cpp",
               "src/user/libc/cpp_runtime.cpp",
               "src/user/libc/main_entry.cpp")
    for source in sources:
        expected = manifest.get("sources", {}).get(source)
        actual = hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
        if expected != actual:
            raise SystemExit(f"Build does not include current {source}; rebuild before testing")

    system_image = build / "xos.img"
    system_hash = hashlib.sha256(system_image.read_bytes()).hexdigest()
    expected_system_hash = manifest.get("artifacts", {}).get("xos.img", {}).get("sha256")
    if expected_system_hash != system_hash:
        raise SystemExit("build/xos.img does not match build/manifest.json")
    probe_hash = hashlib.sha256(image.read_bytes()).hexdigest()
    expected_probe_hash = manifest.get("artifacts", {}).get(image.name, {}).get("sha256")
    if expected_probe_hash != probe_hash:
        raise SystemExit(f"{image.name} does not match its build/manifest.json artifact hash")

    report = {"status": "failed", "build_id": manifest["build_id"],
              "system_image_sha256": system_hash,
              "probe_sha256": probe_hash,
              "paths": {}}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix="xos_tls_exit_") as folder:
            disk = Path(folder) / "tls_exit.img"
            create_fat32(disk, 512)
            transfer(disk, "mkdir", "/bin")
            transfer(disk, "import", "/bin/tls_exit_probe.elf", image)
            guest = boot(disk, "tls_exit_smoke")
            baseline = resources(guest)
            report["baseline_resources"] = baseline
            report["paths"]["main_return"] = verify_path(guest, "", baseline)
            report["paths"]["explicit_exit"] = verify_path(guest, " exit", baseline)
            if resources(guest) != baseline:
                raise AssertionError("task/page/completion state differs after both exit paths")
            report["status"] = "passed"
            print("PASS: normal main return and explicit exit TLS cleanup order")
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        if guest is not None:
            guest.close()
        (build / "tls_exit_smoke_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
