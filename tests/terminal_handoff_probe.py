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
from sdk_receipt import verify_sdk
from work_disk import transfer
from task_smoke import send_bytes
from toolchain import COMMON_FLAGS, X86_FLAGS, tool


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
    sdk = system / 'sdk'
    sdk_receipt = verify_sdk(sdk, manifest)
    fixture = ROOT / 'tests/fixtures/ncursesw/pio_authorized_probe.cpp'
    core_source = ROOT / 'src/user/arch/x86_64/thread_core.cpp'
    report['sdk_tree_sha256'] = sdk_receipt['tree_sha256']
    report['pio_fixture_sha256'] = digest(fixture)
    report['thread_core_source_sha256'] = digest(core_source)
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix="xos_terminal_probe_") as folder:
            obj = Path(folder) / 'pio_authorized.o'
            core = Path(folder) / 'thread_core.o'
            pio = Path(folder) / 'pio_authorized.elf'
            commands = [
                [tool('g++'), *COMMON_FLAGS, *X86_FLAGS, '-I', str(sdk / 'include'), '-I', str(ROOT / 'src/user/include'),
                 '-c', str(fixture), '-o', str(obj)],
                [tool('g++'), *COMMON_FLAGS, *X86_FLAGS, '-I', str(sdk / 'include'), '-I', str(ROOT / 'src/user/include'),
                 '-c', str(core_source), '-o', str(core)],
                [tool('g++'), *X86_FLAGS, '-nostdlib', '-static', '-no-pie',
                 '-Wl,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096',
                 '-T', str(sdk / 'user.ld'), str(sdk / 'crt0.o'), str(obj), str(core), '-Wl,--start-group',
                 str(sdk / 'lib/libxos_loader.a'), str(sdk / 'lib/libxos.a'), '-Wl,--end-group', '-o', str(pio)],
            ]
            for cmd in commands:
                subprocess.run(cmd, check=True)
            if digest(fixture) != report['pio_fixture_sha256'] or digest(core_source) != report['thread_core_source_sha256']:
                raise RuntimeError('PIO fixture or thread core changed while compiling')
            report['pio_elf_sha256'] = digest(pio)
            disk = Path(folder) / "work.img"
            create_fat32(disk, 512)
            transfer(disk, "mkdir", "/bin")
            transfer(disk, "import", "/bin/terminal.elf", terminal)
            transfer(disk, "import", "/bin/tty_app.elf", application)
            transfer(disk, "import", "/bin/pio_auth.elf", pio)
            guest = Guest(image, "terminal_handoff_probe", work_disk=disk, iso=True)
            guest.expect(b"xos64> ", timeout=30)
            send_bytes(guest, b"run\r")
            guest.expect(b"W1_BOOT_READY", timeout=45)
            send_bytes(guest, b"!")
            guest.expect(b"W1_PIO_BOUNDS_OK", timeout=60)
            report['checks'].append('authorized_pio_inside_and_boundary_faults')
            report['checks'].append('authorized_pio_fork_and_exec_revocation')
            report['checks'].append('authorized_pio_explicit_revoke_then_fault')
            report['checks'].append('authorized_pio_multithread_switch_and_revoke')
            report['checks'].append('authorized_irq_empty_timeout_ack_and_close')
            report['checks'].append('authorized_irq_delivery_sequence_and_duplicate_ack')
            report['checks'].append('authorized_irq_blocked_waiter_close')
            guest.expect(b"W1_READ_READY", timeout=45)
            send_bytes(guest, b"R")
            guest.expect(b"W1_READ_OK", timeout=30)
            report["checks"].append("handoff_irq_input_byte")
            guest.expect(b"W1_CANCEL_OK", timeout=30)
            report["checks"].append("pending_read_control_interrupt")
            guest.expect(b"W1_FORK_CHILD", timeout=30)
            report["checks"].append("authenticated_fork_child_terminal_write_and_exit")
            guest.expect(b"W1_LIBC_FORK", timeout=30)
            report["checks"].append("single_thread_libc_fork_terminal_alias")
            guest.expect(b"W1_APP_READY", timeout=30)
            send_bytes(guest, b"A")
            guest.expect(b"W1_SELECT_OK", timeout=30)
            report['checks'].append('single_terminal_select_timeout_errors_and_nonconsuming_ready')
            guest.expect(b"W1_FLUSH_QUEUE_READY", timeout=30)
            send_bytes(guest, b"Q")
            guest.expect(b"W1_FLUSH_FRESH_READY", timeout=30)
            send_bytes(guest, b"F")
            guest.expect(b"W1_TCSA_QUEUE_READY", timeout=30)
            send_bytes(guest, b"X")
            guest.expect(b"W1_TCSA_FRESH_READY", timeout=30)
            send_bytes(guest, b"N")
            guest.expect(b"W1_FLUSH_OK", timeout=30)
            report['checks'].append('tciflush_and_tcsaflush_discard_queued_input_then_accept_new')
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
            (system / 'terminal_handoff_serial.log').write_bytes(guest.output)
            report['serial_sha256'] = hashlib.sha256(guest.output).hexdigest()
            guest.close()
        (system / "terminal_handoff_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS {len(report['checks'])} terminal probe groups | build {manifest['build_id']}")


if __name__ == "__main__":
    main()
