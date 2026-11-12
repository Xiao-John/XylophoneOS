#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""SL3: real minimal C project via guest Make + GCC seed (requires seed cache)."""
import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
import boot_smoke
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from task_smoke import send_bytes, pump
from process_smoke import command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-manifest", type=Path, required=True,
                        help="GCC seed manifest (install_files must exist on disk)")
    parser.add_argument("--seed-root", type=Path, required=True)
    parser.add_argument("--sysroot-manifest", type=Path, required=True)
    parser.add_argument("--sysroot-root", type=Path, required=True)
    parser.add_argument("--report", type=Path,
                        default=ROOT / "build/shell_launch_sl3_make/report.json")
    args = parser.parse_args()

    out = args.report.parent
    out.mkdir(parents=True, exist_ok=True)
    seed = json.loads(args.seed_manifest.read_text())
    sysroot = json.loads(args.sysroot_manifest.read_text())
    # Verify seed inputs exist before booting.
    missing = []
    for entry in seed.get("install_files", []):
        path = args.seed_root / entry["path"]
        if not path.is_file():
            missing.append(entry["path"])
    if missing:
        report = {
            "status": "not_run",
            "reason": "gcc seed cache missing; cannot import toolchain",
            "missing_sample": missing[:5],
            "missing_count": len(missing),
            "seed_manifest": str(args.seed_manifest),
        }
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        print("NOT_RUN SL3 make: gcc seed install_files missing", len(missing))
        return 2

    make_candidates = list((ROOT / ".cache/xos_seed/make").glob("*/make"))
    dash_candidates = list((ROOT / ".cache/xos_seed/dash").glob("*/build/src/dash.runtime"))
    if not make_candidates or not dash_candidates:
        report = {"status": "not_run", "reason": "make or dash binary missing"}
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        print("NOT_RUN SL3 make: make/dash missing")
        return 2
    make_elf = sorted(make_candidates, key=lambda p: p.stat().st_mtime)[-1]
    dash = sorted(dash_candidates, key=lambda p: p.stat().st_mtime)[-1]

    manifest = json.loads((ROOT / "build/manifest.json").read_text())
    report = {
        "status": "failed",
        "checks": [],
        "build_id": manifest["build_id"],
        "make_sha256": hashlib.sha256(make_elf.read_bytes()).hexdigest(),
        "dash_sha256": hashlib.sha256(dash.read_bytes()).hexdigest(),
        "seed_manifest_sha256": hashlib.sha256(args.seed_manifest.read_bytes()).hexdigest(),
    }
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix="xos_sl3make_") as tmp:
            disk = Path(tmp) / "disk.img"
            create_fat32(disk, 2048)
            for d in ("/bin", "/usr", "/usr/bin", "/src", "/out", "/sysroot", "/tests"):
                transfer(disk, "mkdir", d)
            # Import seed + sysroot (same pattern as gcc_seed_smoke).
            from gcc_seed_smoke import import_manifest_files
            seed_files = import_manifest_files(disk, args.seed_root, seed["install_files"], "Seed")
            sys_files = import_manifest_files(disk, args.sysroot_root, sysroot["files"], "sysroot")
            report["seed_files"] = len(seed_files)
            report["sysroot_files"] = len(sys_files)
            transfer(disk, "import", "/usr/bin/make", make_elf)
            transfer(disk, "import", "/usr/bin/dash", dash)

            # Minimal real C project: one .c → one executable.
            (Path(tmp) / "hello.c").write_text(
                "int main(void) { return 0; }\n"
            )
            (Path(tmp) / "Makefile").write_text(
                "CC = /usr/bin/x86_64-elf-gcc\n"
                "CFLAGS = --sysroot=/sysroot -static\n"
                "all: /out/hello.elf\n"
                "/out/hello.elf: /src/hello.c\n"
                "\t$(CC) $(CFLAGS) $< -o $@\n"
            )
            transfer(disk, "import", "/src/hello.c", Path(tmp) / "hello.c")
            transfer(disk, "import", "/tests/Makefile", Path(tmp) / "Makefile")
            script = Path(tmp) / "run_make.sh"
            script.write_text("#!/usr/bin/dash\nmake -B -f /tests/Makefile all\n")
            transfer(disk, "import", "/out/run_make.sh", script)

            base_command = boot_smoke.qemu_command

            def qemu(*args, **kwargs):
                cmd = base_command(*args, **kwargs)
                for i, v in enumerate(cmd):
                    if v.startswith("file=" + str(disk) + ","):
                        cmd[i] = v + ",id=workdisk,node-name=workraw,werror=report,rerror=report"
                return cmd

            with patch.object(boot_smoke, "qemu_command", qemu):
                guest = Guest(ROOT / "build/xos-install.iso", "sl3make", work_disk=disk, iso=True)
            report["qemu_command"] = guest.command
            guest.expect(b"xos64> ", timeout=30)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, timeout=30)
            command(guest, "demo keep", b"demo: keep")
            for pid in (1, 3, 4):
                try:
                    command(guest, f"kill {pid}", b"kill: accepted", timeout=10)
                except Exception:
                    pass
            pump(guest, 0.5)

            # Ordinary bare make -B (no exec-driver / name-based grant).
            r = command(
                guest,
                "make -B -f /tests/Makefile all",
                b"kind=exited code=0",
                timeout=180,
            )
            assert b"cc1" in r or b"x86_64-elf-gcc" in r or b"hello" in r, r[-3000:]
            report["checks"].append("xsh_bare_make_builds_c_project")

            # Run the produced binary via ordinary command.
            r = command(guest, "/out/hello.elf", b"kind=exited code=0", timeout=60)
            report["checks"].append("built_elf_runs_exit0")

            # dash script: bare make (no exec-driver).
            r = command(
                guest,
                "dash /out/run_make.sh",
                b"kind=exited code=0",
                timeout=180,
            )
            report["checks"].append("dash_script_make_builds")

            report["status"] = "passed"
    except Exception as error:
        report["error"] = str(error)
        if guest is not None:
            report["output_tail"] = bytes(guest.output[-4000:]).decode(errors="replace")
        raise
    finally:
        if guest is not None:
            (out / "serial.log").write_bytes(guest.output)
            guest.close()
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print("PASS SL3 make", len(report["checks"]), "checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
