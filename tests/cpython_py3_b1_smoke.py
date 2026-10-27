# SPDX-License-Identifier: Apache-2.0
"""PY3 B1: verify secure entropy and truthful no-RDRAND failure in CPython."""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest, qemu_command
from cpython_py0b_smoke import run
from make_work_disk import create_fat32
from process_smoke import resources
from stage_cpython import sha256, stage_cpython
from task_smoke import pump, send_bytes
from work_disk import transfer

DEFAULT_WORK = ROOT / ".cache/xos_seed/cpython/0739062ab231f71676c8"
DEFAULT_IMAGE = ROOT / "build/cpython_py3_b1/system/xos.img"
FIXTURE = ROOT / "tests/fixtures/cpython_py3_b1/entropy_probe.py"
NATIVE_FIXTURE = ROOT / "tests/fixtures/cpython_py3_b1/getentropy_probe.cpp"
DEFAULT_SDK = ROOT / "build/cpython_py3_b1/threading_sdk"


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


def check_guest(image, disk, name, cpu, argument, marker, native_argument, native_marker):
    guest = Guest(image, name, cpu=cpu, work_disk=disk)
    try:
        guest.expect(b"xos64> ", timeout=30)
        start = len(guest.output)
        send_bytes(guest, b"run\r")
        guest.expect_supervisor(trace=True, start=start, timeout=40)
        pump(guest, 1.0)
        baseline = resources(guest)
        output = run(guest, f"python3 /work/py3b1/entropy_probe.py {argument}".strip(), timeout=180)
        native_output = run(guest, f"/work/py3b1/getentropy_probe.elf {native_argument}".strip())
        after = resources(guest)
        reclaimed = re.findall(r"event=reclaimed pid=\d+ pages=(\d+)", output)
        if marker not in output or "kind=exited code=0" not in output:
            raise AssertionError(f"{name}: expected marker/clean exit missing\n{output[-1600:]}")
        if native_marker not in native_output or "kind=exited code=0" not in native_output:
            raise AssertionError(f"{name}: native getentropy contract failed\n{native_output[-1200:]}")
        if after != baseline or not reclaimed:
            raise AssertionError(f"{name}: resources not restored: {baseline} -> {after}")
        return {
            "name": name,
            "cpu": cpu,
            "marker": marker,
            "native_marker": native_marker,
            "resources_before": baseline,
            "resources_after": after,
            "reclaimed_pages": max(map(int, reclaimed)),
            "tail": output[-1200:],
        }
    finally:
        guest.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=DEFAULT_WORK)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--sdk", type=Path, default=DEFAULT_SDK)
    args = parser.parse_args()
    work, image, sdk = (args.work.resolve(strict=True), args.image.resolve(strict=True),
                        args.sdk.resolve(strict=True))
    stage, stage_manifest = stage_cpython(work, phase="PY3")
    compiler = shutil.which("x86_64-elf-g++")
    if compiler is None:
        raise SystemExit("x86_64-elf-g++ is required for the getentropy contract probe")
    native_probe = ROOT / "build/cpython_py3_b1/getentropy_probe.elf"
    native_probe.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        compiler, "-O2", "-g", "-ffreestanding", "-fno-exceptions", "-fno-rtti",
        "-fno-pic", "-fno-pie", "-fno-stack-protector", "-mno-red-zone",
        "-march=x86-64", "-DXOS_THREADED_RUNTIME", "-ftls-model=local-exec",
        "-I", str(sdk / "include"), "-nostdlib", "-static", "-no-pie",
        "-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096",
        "-T", str(sdk / "user.ld"), str(sdk / "crt0_posix.o"), str(NATIVE_FIXTURE),
        "-Wl,--start-group", str(sdk / "lib/libxos.a"),
        str(sdk / "cpp/lib/libstdc++.a"), str(sdk / "cpp/lib/libsupc++.a"),
        str(sdk / "lib/libc.a"), str(sdk / "lib/libm.a"), str(sdk / "cpp/lib/libgcc.a"),
        "-Wl,--end-group", "-o", str(native_probe),
    ], check=True)
    build_manifest = json.loads((image.parent / "manifest.json").read_text())
    qemu = qemu_command(image)[0]
    report = {
        "phase": "PY3-B1-secure-entropy",
        "status": "failed",
        "system_build_id": build_manifest["build_id"],
        "xos_image_sha256": sha256(image),
        "cpython_fingerprint": stage_manifest["fingerprint"],
        "cpython_sha256": sha256(work / "target_build/python.exe"),
        "native_getentropy_probe_sha256": sha256(native_probe),
        "qemu_version": subprocess.check_output([qemu, "--version"], text=True).splitlines()[0],
        "checks": [],
    }

    with tempfile.TemporaryDirectory(prefix="xos_cpython_py3_b1_") as folder:
        disk = Path(folder) / "work.img"
        create_fat32(disk, 2048)
        install_stage(disk, stage)
        transfer(disk, "mkdir", "/work")
        transfer(disk, "mkdir", "/work/py3b1")
        transfer(disk, "import", "/work/py3b1/entropy_probe.py", FIXTURE)
        transfer(disk, "import", "/work/py3b1/getentropy_probe.elf", native_probe)
        report["checks"].append(check_guest(
            image, disk, "entropy_enabled", "qemu64,+rdrand", "",
            "PY3_B1_ENTROPY_STATISTICS_RANDOM_SECRETS_OK", "",
            "PY3_B1_GETENTROPY_CONTRACT_OK"))
        report["checks"].append(check_guest(
            image, disk, "entropy_unsupported", "qemu64", "unsupported",
            "PY3_B1_UNSUPPORTED_FAILURE_OK", "unsupported",
            "PY3_B1_GETENTROPY_UNSUPPORTED_ENOSYS_OK"))

    report["status"] = "passed"
    output = ROOT / "build/cpython_py3_b1_report.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
