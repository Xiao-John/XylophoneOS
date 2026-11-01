# SPDX-License-Identifier: Apache-2.0
"""Segment 1a gate: build the device_abi probe and run it on the real guest."""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from process_smoke import command
from task_smoke import send_bytes, pump



def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(folder, sdk):
    global SDK
    SDK = sdk
    source = ROOT / "tests/fixtures/device_abi_probe.cpp"
    header = ROOT / "src/shared/include/xos/device_abi.hpp"
    obj = folder / "device_abi_probe.o"
    elf = folder / "device_abi_probe.elf"
    subprocess.run(["x86_64-elf-g++", "-std=c++17", "-O2", "-fno-exceptions",
                    "-fno-rtti", "-nostdinc++", "-I", str(ROOT / "src/shared/include"),
                    "-I", str(SDK / "include"), "-c", str(source), "-o", str(obj)], check=True)
    subprocess.run(["x86_64-elf-g++", "-nostdlib", "-static", "-no-pie",
                    "-Wl,--gc-sections,--build-id=none,--no-undefined",
                    "-T", str(SDK / "user.ld"), str(SDK / "crt0_posix.o"), str(obj),
                    "-Wl,--whole-archive", str(SDK / "lib/libxos.a"), "-Wl,--no-whole-archive",
                    str(SDK / "cpp/lib/libstdc++.a"), str(SDK / "cpp/lib/libsupc++.a"),
                    str(SDK / "lib/libc.a"), str(SDK / "lib/libm.a"),
                    str(SDK / "cpp/lib/libgcc.a"), "-o", str(elf)], check=True)
    return elf, sha256(source), sha256(header)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=ROOT / "build/xos.img")
    parser.add_argument("--output", type=Path, default=ROOT / "build/device_abi_1a")
    parser.add_argument("--sdk", type=Path, default=ROOT / "build/threading_sdk",
                        help="version-matched threading SDK (scripts/build_threading_sdk.py output)")
    a = parser.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="device_abi_1a_") as folder:
        folder = Path(folder)
        elf, source_sha, header_sha = build(folder, a.sdk.resolve())
        disk = folder / "work.img"
        create_fat32(disk, 512)
        transfer(disk, "mkdir", "/bin")
        transfer(disk, "import", "/bin/device_probe.elf", elf)
        report = {"status": "FAILED", "segment": "device_authorization_v1_step1a",
                  "image_sha256": sha256(a.image), "elf_sha256": sha256(elf),
                  "source_sha256": source_sha, "abi_header_sha256": header_sha,
                  "checks": [], "not_run": ["grant_machinery", "map", "irq", "dma"]}
        guest = Guest(a.image, "device_abi_1a", work_disk=disk)
        try:
            guest.expect(b"xos64> ", timeout=30)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, timeout=30)
            pump(guest, 1.0)
            output = command(guest, "exec-file /bin/device_probe.elf", b"kind=exited code=0", timeout=90)
            pump(guest, 0.5)
            passed = b"DEVICE_ABI_PROBE ok" in output and b"kind=exited code=0" in output
            report["checks"].append({"name": "header_validation_negative_probes",
                                     "status": "PASSED" if passed else "FAILED"})
            report["serial_tail"] = output[-2000:].decode("utf-8", "replace")
            report["status"] = "PASSED" if passed else "FAILED"
        finally:
            (out / "report.json").write_text(json.dumps(report, indent=1) + "\n")
            (out / "serial.log").write_bytes(guest.output)
    print(json.dumps({"status": report["status"], "output": str(out)}))
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
