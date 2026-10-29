# SPDX-License-Identifier: MIT AND Apache-2.0
# Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
"""E05: RAM file service, editor, file errors, and loader-from-file."""
import hashlib
import json
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT=Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-net-clock-irq-repair/build/clock_irq/delivery_runs/file_smoke')
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


def editor_line(guest, line, expected=b"| ", timeout=10):
    start = len(guest.output)
    send_bytes(guest, line + b"\r")
    guest.expect(expected, start=start, timeout=timeout)


def main():
    build = ROOT / "build"
    manifest = json.loads((build / "manifest.json").read_text())
    checks = []
    report = {"build_id": manifest["build_id"], "checks": checks, "status": "failed"}
    temporary = tempfile.TemporaryDirectory(prefix="xos_e05_")
    disk = Path(temporary.name) / "work.img"
    disk.write_bytes(make_image())
    guest = Guest(build / "xos.img", "file_smoke", work_disk=disk)
    report["command"] = guest.command
    try:
        for name, digest in manifest["sources"].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
                raise AssertionError(f"Source changed after build: {name}")
        for name, info in manifest["artifacts"].items():
            if hashlib.sha256((build / name).read_bytes()).hexdigest() != info["sha256"]:
                raise AssertionError(f"Artifact mismatch: {name}")
        report["image_sha256"] = manifest["artifacts"]["xos.img"]["sha256"]
        guest.expect(b"xos64> ", timeout=20)
        start = len(guest.output)
        send_bytes(guest, b"run\r")
        guest.expect_any((b"Welcome to Xshell", b"XOS E07 user loader"), start=start, timeout=15)
        guest.expect(b"[files] ready hello.elf", timeout=15)
        guest.expect_supervisor(trace=True, start=start, timeout=15)
        command(guest, "demo keep", b"demo: keep")
        # E03 legacy tasks consume task slots and make the console noisy.
        for pid in (1, 3, 4):
            command(guest, f"kill {pid}", b"kill: accepted")
        pump(guest, 0.3)

        listing = command(guest, "ls", b"hello.elf")
        if not re.search(rb"hello\.elf size=\d+ version=\d+", listing):
            raise AssertionError("file list lacks hello.elf metadata")
        checks.append("file_service_boot_and_list")

        check = command(guest, "filetest", b"[filetest] result=pass")
        for marker in (b"short=read/eof", b"handles=independent", b"locked=preserved", b"write=actual"):
            if marker not in check:
                raise AssertionError(f"filetest missing {marker!r}")
        checks.append("short_read_eof_independent_handles_lock_and_invalid_reject")

        start = len(guest.output)
        send_bytes(guest, b"edit note.txt\r")
        guest.expect(b"[edit] note.txt bytes=0 (new)", start=start, timeout=10)
        for line in (b"first line", b"", b"  two  spaces  ", b"third"):
            editor_line(guest, line)
        send_bytes(guest, b":wq\r")
        guest.expect(b"[edit] saved note.txt", start=start, timeout=10)
        guest.expect(b"sup> ", start=start, timeout=10)
        checks.append("editor_accepts_blank_lines_and_consecutive_spaces")

        cat = command(guest, "cat note.txt", b"first line", timeout=15)
        for marker in (b"\n\n  two  spaces  \n", b"third\n"):
            if marker not in cat:
                raise AssertionError(f"cat lost editor content {marker!r}: {cat[-300:]!r}")
        stat = command(guest, "stat note.txt", b"size=34")
        if b"version=" not in stat:
            raise AssertionError("stat lacks version")
        checks.append("editor_roundtrip_preserves_exact_text")

        start = len(guest.output)
        send_bytes(guest, b"edit note.txt\r")
        guest.expect(b"[edit] note.txt bytes=34 (loaded)", start=start, timeout=10)
        editor_line(guest, b"fourth")
        send_bytes(guest, b":wq\r")
        guest.expect(b"[edit] saved note.txt", start=start, timeout=10)
        guest.expect(b"sup> ", start=start, timeout=10)
        cat = command(guest, "cat note.txt", b"fourth", timeout=15)
        if b"first line" not in cat or b"fourth" not in cat:
            raise AssertionError("modify did not preserve old lines")
        stat = command(guest, "stat note.txt", b"size=41")
        checks.append("editor_modifies_existing_file")

        command(guest, "cat missing.txt", b"[files] cat error=-1")
        command(guest, "stat missing.txt", b"[files] stat error=-1")
        checks.append("file_errors_are_real_and_named")

        command(guest, "rm note.txt", b"removed note.txt")
        listing = command(guest, "ls", b"hello.elf")
        if b"note.txt" in listing:
            raise AssertionError("removed file still listed")
        checks.append("remove_updates_namespace")

        start = len(guest.output)
        send_bytes(guest, b"exec-file hello.elf\r")
        guest.expect(b"hello from file", start=start, timeout=15)
        guest.expect(b"kind=exited code=0", start=start, timeout=15)
        guest.expect(b"sup> ", start=start, timeout=15)
        checks.append("loader_reads_complete_file_snapshot_before_loading")

        report["status"] = "passed"
        print(f"PASS: {len(checks)} E05 checks | build {manifest['build_id']}")
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        guest.close()
        temporary.cleanup()
        (build / "file_smoke_report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
