# SPDX-License-Identifier: Apache-2.0
"""Guest check for the /dev/null device object."""
import hashlib, json, shutil, subprocess, sys, tempfile
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
        with tempfile.TemporaryDirectory(prefix="xos_dev_null_") as folder:
            folder = Path(folder)
            probe = ROOT / "build/dev_null.elf"
            compile_probe(ROOT / "tests/fixtures/dev_null/probe.c", probe, sdk)
            report["probe_sha256"] = sha(probe)
            disk = folder / "work.img"
            create_fat32(disk, 512)
            transfer(disk, "mkdir", "/bin")
            transfer(disk, "import", "/bin/dev_null", probe)
            guest = boot(disk, "dev_null")
            baseline = resources(guest)
            output = command(guest, "exec-driver /bin/dev_null run",
                             b"kind=exited code=", timeout=120)
            if b"kind=exited code=0" not in output or b"DEV_NULL_OK" not in output:
                raise AssertionError(output[-4000:])
            report["checks"].append("dev_null_behaved")
            report["probe_output"] = output.decode("utf-8", "replace")[-1200:]
            after = resources(guest)
            if after != baseline:
                raise AssertionError(f"resource leak: {baseline} -> {after}")
            report["checks"].append("resources_restored")
            report["status"] = "passed"
    finally:
        if guest is not None:
            guest.close()
    (ROOT / "build/dev_null.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": report["checks"],
                      "build_id": report["build_id"]}))


if __name__ == "__main__":
    main()
