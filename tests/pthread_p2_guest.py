# SPDX-License-Identifier: Apache-2.0
"""Guest check for the P2 pthread surface (sem/barrier/spin/names/attrs)."""
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


def compile_probe(source, output, sdk, threaded):
    compiler = shutil.which("x86_64-elf-gcc") or "x86_64-elf-gcc"
    libgcc = subprocess.check_output([compiler, "-print-libgcc-file-name"], text=True).strip()
    flags = ["-idirafter", str(sdk / "include"),
             "-D_POSIX_THREADS=1", "-D_POSIX_READER_WRITER_LOCKS=200809L",
             "-D_UNIX98_THREAD_MUTEX_ATTRIBUTES=1", "-DXOS_THREADED_RUNTIME"]
    libraries = [str(sdk / "lib/libxos.a"), str(sdk / "lib/libc.a"),
                 str(sdk / "lib/libm.a")]
    loader = sdk / "lib/libxos_loader.a"
    if loader.is_file():
        libraries.insert(1, str(loader))
    subprocess.run([
        compiler, "-O2", "-mno-red-zone", "-fno-pie", "-fno-pic", "-fno-stack-protector",
        *flags, "-nostdlib", "-static", "-no-pie",
        "-T", str(sdk / "user.ld"), str(sdk / "crt0_posix.o"), str(source),
        "-Wl,--start-group", *libraries, libgcc, "-Wl,--end-group", "-o", str(output),
    ], check=True)


def main():
    system = json.loads((ROOT / "build/manifest.json").read_text())
    single_sdk, threaded_sdk = ROOT / "build/sdk", ROOT / "build/threading_sdk"
    report = {"status": "failed", "build_id": system["build_id"], "checks": []}
    guest = None
    try:
        if not (threaded_sdk / "lib/libxos.a").is_file():
            raise SystemExit("build/threading_sdk is missing; run build_threading_sdk.py first")
        with tempfile.TemporaryDirectory(prefix="xos_pthread_p2_") as folder:
            folder = Path(folder)
            single = ROOT / "build/pthread_p2_single.elf"
            threaded = ROOT / "build/pthread_p2_threaded.elf"
            compile_probe(ROOT / "tests/fixtures/pthread_p2/single.c", single, single_sdk, False)
            compile_probe(ROOT / "tests/fixtures/pthread_p2/threaded.c", threaded, threaded_sdk, True)
            report["probes"] = {"single": sha(single), "threaded": sha(threaded)}
            disk = folder / "work.img"
            create_fat32(disk, 512)
            transfer(disk, "mkdir", "/bin")
            transfer(disk, "import", "/bin/p2_single", single)
            transfer(disk, "import", "/bin/p2_threaded", threaded)
            guest = boot(disk, "pthread_p2")
            baseline = resources(guest)
            for name, expected in (("p2_single", b"PTHREAD_P2_SINGLE_OK"),
                                   ("p2_threaded", b"PTHREAD_P2_OK")):
                output = command(guest, f"exec-driver /bin/{name} run",
                                 b"kind=exited code=", timeout=180)
                if b"kind=exited code=0" not in output or expected not in output:
                    raise AssertionError(output[-4000:])
                report["checks"].append(name)
            after = resources(guest)
            if after != baseline:
                raise AssertionError(f"resource leak: {baseline} -> {after}")
            report["checks"].append("resources_restored")
            report["status"] = "passed"
    finally:
        if guest is not None:
            guest.close()
    (ROOT / "build/pthread_p2.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": report["checks"],
                      "build_id": report["build_id"]}))


if __name__ == "__main__":
    main()
