# SPDX-License-Identifier: MIT AND Apache-2.0
# Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
"""E07: normal sync/reboot persistence, deletion, and file-count save failure."""
import json
import sys
import tempfile
from pathlib import Path

ROOT=Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-net-clock-irq-repair/build/clock_irq/delivery_runs/persist_smoke')
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from boot_smoke import Guest
from task_smoke import send_bytes, pump
from make_work_disk import make_image


def command(guest, line, expected, timeout=15):
    start = len(guest.output)
    send_bytes(guest, line.encode() + b"\r")
    guest.expect(expected, start=start, timeout=timeout)
    guest.expect(b"sup> ", start=start, timeout=timeout)
    return bytes(guest.output)[start:]


def edit_lines(guest, name, lines, *, expect_new=False, expect_loaded=None):
    start = len(guest.output)
    send_bytes(guest, f"edit {name}\r".encode())
    guest.expect(b"(new)" if expect_new else b"(loaded)", start=start, timeout=10)
    if expect_loaded is not None:
        guest.expect(f"bytes={expect_loaded}".encode(), start=start, timeout=10)
    for line in lines:
        line_start = len(guest.output)
        send_bytes(guest, line + b"\r")
        guest.expect(b"| ", start=line_start, timeout=10)
    send_bytes(guest, b":wq\r")
    guest.expect(b"[edit] saved ", start=start, timeout=12)
    guest.expect(b"sup> ", start=start, timeout=12)


def boot(disk, name):
    guest = Guest(ROOT / "build/xos.img", name, work_disk=disk)
    guest.expect(b"xos64> ", timeout=20)
    start = len(guest.output)
    send_bytes(guest, b"run\r")
    guest.expect_supervisor(trace=True, start=start, timeout=20)
    command(guest, "demo keep", b"demo: keep")
    for pid in (1, 3, 4):
        command(guest, f"kill {pid}", b"kill: accepted")
    pump(guest, 0.3)
    return guest


def main():
    build = ROOT / "build"
    manifest = json.loads((build / "manifest.json").read_text())
    checks = []
    report = {"build_id": manifest["build_id"], "checks": checks, "status": "failed"}
    temporary = tempfile.TemporaryDirectory(prefix="xos_e07_")
    disk = Path(temporary.name) / "work.img"
    disk.write_bytes(make_image())
    guest = None
    try:
        guest = boot(disk, "persist_boot1")
        guest.expect(b"[files] ready hello.elf", timeout=15)
        edit_lines(guest, "note.txt", [b"first line", b"", b"  two  spaces  ", b"third"],
                   expect_new=True)
        edit_lines(guest, "note.txt", [b"fourth"], expect_loaded=34)
        edit_lines(guest, "del.txt", [b"remove me"], expect_new=True)
        command(guest, "rm del.txt", b"removed del.txt")
        command(guest, "sync", b"[files] sync=ok")
        guest.close()
        guest = None
        checks.append("first_boot_create_overwrite_delete_sync")

        guest = boot(disk, "persist_boot2")
        guest.expect(f"[files] hello.elf present bytes={(build / 'user_hello.image.elf').stat().st_size}".encode(), timeout=15)
        cat = command(guest, "cat note.txt", b"first line", timeout=15)
        for marker in (b"\n\n  two  spaces  \n", b"third\n", b"fourth\n"):
            if marker not in cat:
                raise AssertionError(f"persisted text mismatch: {cat[-400:]!r}")
        listing = command(guest, "ls", b"hello.elf", timeout=15)
        if b"del.txt" in listing.lower():
            raise AssertionError("deleted file returned after reboot")
        checks.append("second_boot_verifies_content_and_deletion")

        start = len(guest.output)
        send_bytes(guest, b"exec-file hello.elf\r")
        guest.expect(b"hello from file", start=start, timeout=15)
        guest.expect(b"kind=exited code=0", start=start, timeout=15)
        guest.expect(b"sup> ", start=start, timeout=15)
        checks.append("second_boot_executes_persisted_elf")

        # E08 removes the old four-file cap; keep persistence regression and
        # prove the fifth ordinary file is now really saved.
        edit_lines(guest, "a.txt", [b"keep me"], expect_new=True)
        edit_lines(guest, "b.txt", [b"second"], expect_new=True)
        edit_lines(guest, "c.txt", [b"fifth file"], expect_new=True)
        command(guest, "cat c.txt", b"fifth file")
        checks.append("expanded_namespace_saves_fifth_file")

        command(guest, "sync", b"[files] sync=ok")
        report["disk_bytes"] = disk.stat().st_size
        report["status"] = "passed"
        print(f"PASS: {len(checks)} E07 checks | build {manifest['build_id']}")
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        if guest is not None:
            guest.close()
        temporary.cleanup()
        (build / "persist_smoke_report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
