#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""SL1: identity-carried create authority (shell_launch contract) guest probe."""
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
    out = ROOT / "build/shell_launch_sl1"
    out.mkdir(parents=True, exist_ok=True)
    sdk = ROOT / "build/sdk"
    src = ROOT / "tests/fixtures/shell_launch/sl1_authority.cpp"
    manifest = json.loads((ROOT / "build/manifest.json").read_text())
    obj = out / "sl1_probe.o"
    elf = out / "sl1_probe.elf"
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
    report = {
        "status": "failed",
        "checks": [],
        "build_id": manifest["build_id"],
        "fixture_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
        "elf_sha256": hashlib.sha256(elf.read_bytes()).hexdigest(),
    }
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix="xos_sl1_") as tmp:
            disk = Path(tmp) / "disk.img"
            create_fat32(disk, 512)
            transfer(disk, "mkdir", "/bin")
            transfer(disk, "import", "/sl1_probe.elf", elf)
            base_command = boot_smoke.qemu_command

            def qemu(*args, **kwargs):
                cmd = base_command(*args, **kwargs)
                for i, v in enumerate(cmd):
                    if v.startswith("file=" + str(disk) + ","):
                        cmd[i] = v + ",id=workdisk,node-name=workraw,werror=report,rerror=report"
                return cmd

            with patch.object(boot_smoke, "qemu_command", qemu):
                guest = Guest(ROOT / "build/xos.img", "sl1probe", work_disk=disk)
            report["qemu_command"] = guest.command
            guest.expect(b"xos64> ", timeout=30)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, timeout=30)
            # Free demo tasks so endpoint/completion pools are available.
            for pid in (1, 3, 4):
                try:
                    command(guest, f"kill {pid}", b"kill: accepted", timeout=10)
                except Exception:
                    pass
            pump(guest, 0.5)
            # exec-driver grants legacy depth (and SL1 can_create via grant).
            result = command(guest, "exec-driver /sl1_probe.elf", b"SL1_PROBE_PASS", timeout=60)
            text = result.decode(errors="replace")
            required = [
                "SL1_T1_OK",
                "SL1_T1_CHILD_OK",
                "SL1_T2_OK",
                "SL1_T3_OK",
                "SL1_T4_OK",
                "SL1_T5_OK",
                "SL1_PROBE_PASS",
            ]
            for token in required:
                if token not in text:
                    raise AssertionError(f"missing {token} in {text!r}")
            assert "kind=exited code=0" in text, text
            report["checks"] = required
            report["output"] = text
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
    print("PASS SL1 authority", len(report["checks"]), "checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
