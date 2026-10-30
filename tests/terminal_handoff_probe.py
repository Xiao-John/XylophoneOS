# SPDX-License-Identifier: Apache-2.0
"""Run the dedicated COM1 handoff probe after committing all source changes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from task_smoke import send_bytes


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", type=Path, required=True)
    args = parser.parse_args()
    system = args.system.resolve()
    if ROOT / "build" not in system.parents:
        parser.error("system must be an isolated build subdirectory")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise SystemExit("commit all changes before running the guest probe")
    manifest = json.loads((system / "manifest.json").read_text())
    if not manifest.get("terminal_supervisor_probe"):
        raise SystemExit("system was not built with --terminal-supervisor-probe")
    for name, expected in manifest["sources"].items():
        source = ROOT / name
        if not source.is_file() or digest(source) != expected:
            raise SystemExit(f"source differs from build manifest: {name}")
    image = system / "xos-install.iso"
    terminal = system / "user_terminal.image.elf"
    application = system / "user_terminal_app_probe.image.elf"
    for path in (image, terminal, application):
        entry = manifest["artifacts"].get(path.name)
        if not entry or digest(path) != entry["sha256"]:
            raise SystemExit(f"artifact differs from build manifest: {path.name}")
    report = {"status": "failed", "build_id": manifest["build_id"],
              "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "image_sha256": digest(image), "terminal_sha256": digest(terminal),
              "application_sha256": digest(application), "checks": []}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix="xos_terminal_probe_") as folder:
            disk = Path(folder) / "work.img"
            create_fat32(disk, 512)
            transfer(disk, "mkdir", "/bin")
            transfer(disk, "import", "/bin/terminal.elf", terminal)
            transfer(disk, "import", "/bin/tty_app.elf", application)
            guest = Guest(image, "terminal_handoff_probe", work_disk=disk, iso=True)
            guest.expect(b"xos64> ", timeout=30)
            send_bytes(guest, b"run\r")
            guest.expect(b"W1_BOOT_READY", timeout=45)
            send_bytes(guest, b"!")
            guest.expect(b"W1_READ_READY", timeout=45)
            send_bytes(guest, b"R")
            guest.expect(b"W1_READ_OK", timeout=30)
            report["checks"].append("handoff_irq_input_byte")
            guest.expect(b"W1_CANCEL_OK", timeout=30)
            report["checks"].append("pending_read_control_interrupt")
            guest.expect(b"W1_APP_READY", timeout=30)
            send_bytes(guest, b"A")
            guest.expect(b"W1_APP_OK", timeout=30)
            guest.expect(b"W1_APP_REAPED", timeout=30)
            report["checks"].append("authenticated_application_start_and_exit")
            guest.expect(b"W1_REAUTHORIZE_OK", timeout=30)
            report["checks"].append("normal_stop_and_explicit_reauthorization")
            report["status"] = "passed"
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        if guest:
            guest.close()
        (system / "terminal_handoff_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS {len(report['checks'])} terminal probe groups | build {manifest['build_id']}")


if __name__ == "__main__":
    main()
