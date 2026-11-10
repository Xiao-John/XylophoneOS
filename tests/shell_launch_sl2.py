#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""SL2: both shells use inherit-create; no name-based authorization."""
import hashlib
import json
import re
import subprocess
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
from toolchain import COMMON_FLAGS, X86_FLAGS, tool


def main() -> int:
    out = ROOT / "build/shell_launch_sl2"
    out.mkdir(parents=True, exist_ok=True)
    sdk = ROOT / "build/sdk"
    src = ROOT / "tests/fixtures/shell_launch/sl1_authority.cpp"
    obj = out / "sl2_probe.o"
    elf = out / "sl2_probe.elf"
    subprocess.run(
        [tool("g++"), *COMMON_FLAGS, *X86_FLAGS, "-I", str(sdk / "include"),
         "-c", str(src), "-o", str(obj)],
        check=True,
    )
    subprocess.run(
        [tool("g++"), *X86_FLAGS, "-nostdlib", "-static", "-no-pie",
         "-Wl,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096",
         "-T", str(sdk / "user.ld"), str(sdk / "crt0.o"), str(obj),
         "-Wl,--start-group", str(sdk / "lib/libxos.a"), str(sdk / "lib/libxos_loader.a"),
         "-Wl,--end-group", "-o", str(elf)],
        check=True,
    )
    # dash for the in-shell leg
    dash_candidates = list((ROOT / ".cache/xos_seed/dash").glob("*/build/src/dash.runtime"))
    if not dash_candidates:
        raise SystemExit("dash.runtime not found; run scripts/build_dash.py first")
    dash = sorted(dash_candidates, key=lambda p: p.stat().st_mtime)[-1]

    report = {"status": "failed", "checks": [], "build_id": None, "elf_sha256": hashlib.sha256(elf.read_bytes()).hexdigest()}
    guest = None
    try:
        report["build_id"] = json.loads((ROOT / "build/manifest.json").read_text())["build_id"]
        with tempfile.TemporaryDirectory(prefix="xos_sl2_") as tmp:
            disk = Path(tmp) / "disk.img"
            create_fat32(disk, 512)
            transfer(disk, "mkdir", "/bin")
            transfer(disk, "mkdir", "/usr")
            transfer(disk, "mkdir", "/usr/bin")
            transfer(disk, "import", "/bin/sl2_probe", elf)
            transfer(disk, "import", "/bin/fauxtool", elf)  # renamed twin
            transfer(disk, "import", "/usr/bin/dash", dash)
            transfer(disk, "mkdir", "/out")
            script = Path(tmp) / "q.sh"
            script.write_text("#!/usr/bin/dash\n/bin/sl2_probe query\n")
            transfer(disk, "import", "/out/q.sh", script)
            base_command = boot_smoke.qemu_command

            def qemu(*args, **kwargs):
                cmd = base_command(*args, **kwargs)
                for i, v in enumerate(cmd):
                    if v.startswith("file=" + str(disk) + ","):
                        cmd[i] = v + ",id=workdisk,node-name=workraw,werror=report,rerror=report"
                return cmd

            with patch.object(boot_smoke, "qemu_command", qemu):
                guest = Guest(ROOT / "build/xos-install.iso", "sl2probe", work_disk=disk, iso=True)
            report["qemu_command"] = guest.command
            guest.expect(b"xos64> ", timeout=30)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, timeout=30)
            for pid in (1, 3, 4):
                try:
                    command(guest, f"kill {pid}", b"kill: accepted", timeout=10)
                except Exception:
                    pass
            pump(guest, 0.5)

            # 1) xsh bare command → inherit create
            r = command(guest, "sl2_probe query", b"SL1_QUERY_OK", timeout=45)
            assert b"SL1_OWN_QUERY=1" in r, r
            report["checks"].append("xsh_bare_inherits_create")

            # 2) renamed twin gets the same authority
            r = command(guest, "fauxtool query", b"SL1_QUERY_OK", timeout=45)
            assert b"SL1_OWN_QUERY=1" in r, r
            report["checks"].append("renamed_program_same_authority")

            # 3) exec-file remains restricted (historical entry)
            r = command(guest, "exec-file /bin/sl2_probe query", b"SL1_QUERY_OK", timeout=45)
            assert b"SL1_OWN_QUERY=0" in r, r
            report["checks"].append("exec_file_no_create")

            # 4) dash script → posix_spawn inherit (no gcc/make name case)
            r = command(guest, "dash /out/q.sh", b"SL1_QUERY_OK", timeout=45)
            assert b"SL1_OWN_QUERY=1" in r, r
            report["checks"].append("dash_posix_spawn_inherits_create")

            # 5) old SDK boundary: exec-driver still grants legacy create (compat table).
            r = command(guest, "exec-driver /bin/sl2_probe query", b"SL1_QUERY_OK", timeout=45)
            assert b"SL1_OWN_QUERY=1" in r, r
            report["checks"].append("exec_driver_legacy_grant_still_works")

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
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS SL2", len(report["checks"]), "checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
