# SPDX-License-Identifier: Apache-2.0
"""Guest check for P0 clock functions (clock_gettime/clock_getres/clock_settime/
clock_nanosleep/nanosleep)."""
import json, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from make_work_disk import create_fat32
from work_disk import transfer
from e08_storage_smoke import boot
from process_smoke import command, resources


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


def dash_runtime():
    candidates = sorted((ROOT / ".cache/xos_seed/dash").glob("*/build/src/dash.runtime"))
    if not candidates:
        raise SystemExit("dash runtime missing; run scripts/build_dash.py first")
    return candidates[-1]


def main():
    system = json.loads((ROOT / "build/manifest.json").read_text())
    sdk = ROOT / "build/sdk"
    report = {"status": "failed", "build_id": system["build_id"], "checks": []}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix="xos_clock_") as folder:
            folder = Path(folder)
            probe = ROOT / "build/posix_clock.elf"
            compile_probe(ROOT / "tests/fixtures/posix_clock/probe.c", probe, sdk)
            disk = folder / "work.img"
            create_fat32(disk, 512)
            for directory in ("/usr", "/usr/bin", "/tests"):
                transfer(disk, "mkdir", directory)
            transfer(disk, "import", "/usr/bin/clock_probe", probe)
            transfer(disk, "import", "/usr/bin/dash", dash_runtime())
            script = folder / "clock.sh"
            script.write_text("/usr/bin/clock_probe\necho dash_rc=$?\n")
            transfer(disk, "import", "/tests/clock.sh", script)
            guest = boot(disk, "posix_clock")
            baseline = resources(guest)
            output = command(guest, "clock_probe", b"kind=exited code=", timeout=180)
            if b"kind=exited code=0" not in output or b"CLOCK_OK" not in output:
                raise AssertionError(output[-4000:])
            report["checks"].append("clock_unit")
            report["probe_output"] = output.decode("utf-8", "replace")[-2000:]
            output = command(guest, "dash /tests/clock.sh", b"dash_rc=", timeout=180)
            if b"CLOCK_OK" not in output or b"dash_rc=0" not in output:
                raise AssertionError(output[-4000:])
            report["checks"].append("clock_dash")
            after = resources(guest)
            if after != baseline:
                raise AssertionError(f"resource leak: {baseline} -> {after}")
            report["checks"].append("resources_restored")
            report["status"] = "passed"
    finally:
        if guest is not None:
            guest.close()
        (ROOT / "build/posix_clock.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": report["checks"],
                      "build_id": report["build_id"]}))


if __name__ == "__main__":
    main()
