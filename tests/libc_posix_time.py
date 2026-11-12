# SPDX-License-Identifier: Apache-2.0
"""Link and run a probe for times/clock/timespec_get/clock_gettime/utime/chmod/chown."""
import hashlib
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
from process_smoke import command, resources


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compile_probe(source, output, sdk):
    compiler = shutil.which("x86_64-elf-gcc") or "x86_64-elf-gcc"
    libgcc = subprocess.check_output([compiler, "-print-libgcc-file-name"], text=True).strip()
    subprocess.run([
        compiler, "-O2", "-mno-red-zone", "-fno-pie", "-fno-pic", "-fno-stack-protector",
        "-idirafter", str(sdk / "include"), "-nostdlib", "-static", "-no-pie",
        "-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096",
        "-T", str(sdk / "user.ld"), str(sdk / "crt0_posix.o"), str(source),
        "-Wl,--start-group", str(sdk / "lib/libxos.a"), str(sdk / "lib/libxos_loader.a"),
        str(sdk / "lib/libc.a"), str(sdk / "lib/libm.a"), libgcc, "-Wl,--end-group",
        "-o", str(output),
    ], check=True)


def main():
    system = json.loads((ROOT / "build/manifest.json").read_text())
    sdk = ROOT / "build/sdk"
    report = {"status": "failed", "build_id": system["build_id"],
              "image_sha256": sha(ROOT / "build/xos-install.iso"), "checks": []}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix="xos_libc_time_") as folder:
            folder = Path(folder)
            probe = ROOT / "build/libc_posix_time.elf"
            compile_probe(ROOT / "tests/fixtures/libc_posix_time/probe.c", probe, sdk)
            report["probe_sha256"] = sha(probe)
            disk = folder / "work.img"
            create_fat32(disk, 512)
            for name in ("/bin", "/case"):
                transfer(disk, "mkdir", name)
            payload = folder / "file"
            payload.write_text("libc time probe\n")
            transfer(disk, "import", "/case/file", payload)
            transfer(disk, "import", "/bin/probe", probe)
            guest = boot(disk, "libc_posix_time")
            baseline = resources(guest)
            output = command(guest, "exec-driver /bin/probe run",
                             b"kind=exited code=", timeout=120)
            if b"kind=exited code=0" not in output or b"LIBC_TIME_OK" not in output:
                raise AssertionError(output[-4000:])
            report["checks"].append("symbols_linked_and_behaved")
            report["probe_output"] = output.decode("utf-8", "replace")[-1200:]
            after = resources(guest)
            if after != baseline:
                raise AssertionError(f"resource leak: {baseline} -> {after}")
            report["checks"].append("resources_restored")
            report["resources"] = list(after)
            report["status"] = "passed"
    finally:
        if guest is not None:
            guest.close()
    (ROOT / "build/libc_posix_time.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": report["checks"],
                      "build_id": report["build_id"]}))


if __name__ == "__main__":
    main()
