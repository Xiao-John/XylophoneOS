#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""SL3: ordinary xos-diag invocation returns to the shell with correct codes."""
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
    out = ROOT / "build/shell_launch_sl3"
    out.mkdir(parents=True, exist_ok=True)
    system = ROOT / "build"
    diag_elf = system / "user_xos_diag.image.elf"
    fault_elf = system / "user_fault.image.elf"
    hello_elf = system / "user_hello.image.elf"
    for path in (diag_elf, fault_elf, hello_elf, system / "xos-install.iso"):
        if not path.is_file():
            raise SystemExit(f"missing build artifact: {path}")
    dash_candidates = list((ROOT / ".cache/xos_seed/dash").glob("*/build/src/dash.runtime"))
    if not dash_candidates:
        raise SystemExit("dash.runtime not found; run scripts/build_dash.py first")
    dash = sorted(dash_candidates, key=lambda p: p.stat().st_mtime)[-1]

    manifest = json.loads((system / "manifest.json").read_text())
    report = {
        "status": "failed",
        "checks": [],
        "build_id": manifest["build_id"],
        "diag_sha256": hashlib.sha256(diag_elf.read_bytes()).hexdigest(),
        "fault_sha256": hashlib.sha256(fault_elf.read_bytes()).hexdigest(),
        "hello_sha256": hashlib.sha256(hello_elf.read_bytes()).hexdigest(),
        "dash_sha256": hashlib.sha256(dash.read_bytes()).hexdigest(),
    }
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix="xos_sl3_") as tmp:
            disk = Path(tmp) / "disk.img"
            create_fat32(disk, 512)
            transfer(disk, "mkdir", "/bin")
            transfer(disk, "mkdir", "/usr")
            transfer(disk, "mkdir", "/usr/bin")
            transfer(disk, "mkdir", "/out")
            transfer(disk, "mkdir", "/FAULTS")
            transfer(disk, "import", "/usr/bin/xos-diag", diag_elf)
            transfer(disk, "import", "/bin/fault.elf", fault_elf)
            transfer(disk, "import", "/bin/hello.elf", hello_elf)
            transfer(disk, "import", "/usr/bin/dash", dash)
            # dash scripts: ordinary bare xos-diag (no exec / exec-driver).
            for name, body in (
                ("diag_normal.sh", "#!/usr/bin/dash\n/usr/bin/xos-diag /bin/hello.elf\n"),
                ("diag_fault.sh", "#!/usr/bin/dash\n/usr/bin/xos-diag /bin/fault.elf\n"),
                ("diag_missing.sh", "#!/usr/bin/dash\n/usr/bin/xos-diag /bin/missing\n"),
            ):
                script = Path(tmp) / name
                script.write_text(body)
                transfer(disk, "import", "/out/" + name, script)

            base_command = boot_smoke.qemu_command

            def qemu(*args, **kwargs):
                cmd = base_command(*args, **kwargs)
                for i, v in enumerate(cmd):
                    if v.startswith("file=" + str(disk) + ","):
                        cmd[i] = v + ",id=workdisk,node-name=workraw,werror=report,rerror=report"
                return cmd

            with patch.object(boot_smoke, "qemu_command", qemu):
                guest = Guest(system / "xos-install.iso", "sl3diag", work_disk=disk, iso=True)
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

            # 1) xsh bare xos-diag normal → exit 0, back to supervisor, no bundle.
            r = command(guest, "xos-diag /bin/hello.elf", b"kind=exited code=0", timeout=60)
            assert b"[xos-diag] kind=exited code=0" in r, r
            assert b"[fault-bundle] saved" not in r, r
            report["checks"].append("xsh_bare_diag_normal_exit0")

            # 2) xsh bare xos-diag fault → 128 + bundle saved.
            r = command(guest, "xos-diag /bin/fault.elf", b"kind=exited code=128", timeout=60)
            assert b"[xos-diag] kind=faulted vector=14" in r, r
            match = re.search(rb"\[fault-bundle\] saved (/FAULTS/[0-9a-f]{32})", r)
            assert match, r[-3000:]
            report["fault_bundle_path"] = match.group(1).decode()
            report["checks"].append("xsh_bare_diag_fault_128_bundle")

            # 3) xsh bare xos-diag missing → 127, no bundle.
            r = command(guest, "xos-diag /bin/missing", b"kind=exited code=127", timeout=60)
            assert b"cannot resolve program" in r, r
            assert b"[fault-bundle] saved" not in r, r
            report["checks"].append("xsh_bare_diag_missing_127")

            # 4) xsh diag builtin still works (historical diagnosed entry).
            r = command(guest, "diag /bin/fault.elf", b"kind=faulted", timeout=60)
            assert b"[fault-bundle] saved" in r, r
            report["checks"].append("xsh_diag_builtin_fault")

            # 5) dash ordinary script: normal / fault / missing (no exec-driver).
            r = command(guest, "dash /out/diag_normal.sh", b"kind=exited code=0", timeout=60)
            assert b"[xos-diag] kind=exited code=0" in r, r
            report["checks"].append("dash_script_diag_normal")

            r = command(guest, "dash /out/diag_fault.sh", b"kind=exited code=128", timeout=60)
            assert b"[xos-diag] kind=faulted vector=14" in r, r
            assert b"[fault-bundle] saved" in r, r
            report["checks"].append("dash_script_diag_fault")

            r = command(guest, "dash /out/diag_missing.sh", b"kind=exited code=127", timeout=60)
            assert b"cannot resolve program" in r, r
            report["checks"].append("dash_script_diag_missing")

            # 6) Historical restricted entry: exec-file grants no create authority,
            # so xos-diag cannot spawn its target (compat: denied, exit 126).
            r = command(guest, "exec-file /usr/bin/xos-diag /bin/hello.elf",
                        b"kind=exited code=126", timeout=60)
            assert b"launch error=-1" in r, r
            report["checks"].append("exec_file_diag_no_create_126")

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
    print("PASS SL3 diag", len(report["checks"]), "checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
