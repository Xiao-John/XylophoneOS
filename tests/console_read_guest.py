# SPDX-License-Identifier: Apache-2.0
"""Guest check: read() on the console blocks until a key and maps CR to NL."""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from make_work_disk import create_fat32
from work_disk import transfer
from e08_storage_smoke import boot
from task_smoke import send_bytes, pump


def compile_probe(source, output, sdk):
    compiler = shutil.which("x86_64-elf-gcc") or "x86_64-elf-gcc"
    libgcc = subprocess.check_output([compiler, "-print-libgcc-file-name"], text=True).strip()
    subprocess.run([
        compiler, "-O2", "-mno-red-zone", "-fno-pie", "-fno-pic", "-fno-stack-protector",
        "-idirafter", str(sdk / "include"), "-nostdlib", "-static", "-no-pie",
        "-T", str(sdk / "user.ld"), str(sdk / "crt0_posix.o"), str(source),
        "-Wl,--start-group", str(sdk / "lib/libxos.a"), str(sdk / "lib/libxos_loader.a"),
        str(sdk / "lib/libc.a"), str(sdk / "lib/libm.a"), libgcc, "-Wl,--end-group",
        "-o", str(output),
    ], check=True)


def main():
    system = json.loads((ROOT / "build/manifest.json").read_text())
    sdk = ROOT / "build/sdk"
    report = {"status": "failed", "build_id": system["build_id"], "checks": []}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix="xos_console_read_") as folder:
            folder = Path(folder)
            probe = ROOT / "build/console_read.elf"
            compile_probe(ROOT / "tests/fixtures/console_read/probe.c", probe, sdk)
            disk = folder / "work.img"
            create_fat32(disk, 512)
            transfer(disk, "mkdir", "/bin")
            transfer(disk, "import", "/bin/console_read", probe)
            guest = boot(disk, "console_read")
            guest.expect(b"xos64> ", timeout=120)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(timeout=90)
            pump(guest, 0.8)
            mark = len(guest.output)
            send_bytes(guest, b"exec-driver /bin/console_read run\r")
            pump(guest, 1.5)
            blocked = len(guest.output)
            if b"read=" in guest.output[mark:]:
                raise AssertionError("read() returned before any key was sent")
            send_bytes(guest, b"ab\r")
            pump(guest, 1.5)
            text = bytes(guest.output[blocked:]).decode("utf-8", "replace")
            expected = "read=3 61 62 0a"
            if expected not in text:
                raise AssertionError(text[-2000:])
            report["checks"].append("blocks_until_input")
            report["checks"].append("cr_maps_to_nl")
            report["probe_output"] = text[-400:]
            report["status"] = "passed"
    finally:
        if guest is not None:
            guest.close()
    (ROOT / "build/console_read.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": report["checks"],
                      "build_id": report["build_id"]}))


if __name__ == "__main__":
    main()
