"""E07: a physically full FAT16 volume must fail saves without touching old data."""
import json
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from boot_smoke import Guest
from task_smoke import send_bytes, pump
from make_work_disk import make_image, DATA_START, FAT_SECTORS, RESERVED, ROOT_SECTORS

SECTOR = 512
CLUSTER_BYTES = 8 * SECTOR
DATA_CLUSTERS = (16 * 1024 * 1024 // SECTOR - DATA_START) // 8
ROOT_OFFSET = (RESERVED + 2 * FAT_SECTORS) * SECTOR
NOTE_CLUSTER = 2
FILLER_CLUSTER = 3
FILLER_SIZE = (DATA_CLUSTERS - 2) * CLUSTER_BYTES


def root_entry(name, cluster, size):
    entry = bytearray(32)
    entry[0:11] = name
    entry[11] = 0x20
    struct.pack_into("<H", entry, 26, cluster & 0xFFFF)
    struct.pack_into("<I", entry, 28, size)
    return entry


def set_fat(data, cluster, value):
    for index in range(2):
        offset = (RESERVED + index * FAT_SECTORS) * SECTOR + cluster * 2
        struct.pack_into("<H", data, offset, value)


def make_full_image():
    data = bytearray(make_image())
    data[ROOT_OFFSET:ROOT_OFFSET + 32] = root_entry(b"NOTE    TXT", NOTE_CLUSTER, 4)
    data[ROOT_OFFSET + 32:ROOT_OFFSET + 64] = root_entry(b"FILLER  BIN", FILLER_CLUSTER, FILLER_SIZE)
    set_fat(data, NOTE_CLUSTER, 0xFFFF)
    for cluster in range(FILLER_CLUSTER, FILLER_CLUSTER + (DATA_CLUSTERS - 2)):
        nxt = 0xFFFF if cluster == FILLER_CLUSTER + (DATA_CLUSTERS - 3) else cluster + 1
        set_fat(data, cluster, nxt)
    data[DATA_START * SECTOR + (NOTE_CLUSTER - 2) * CLUSTER_BYTES:
         DATA_START * SECTOR + (NOTE_CLUSTER - 2) * CLUSTER_BYTES + 4] = b"old\n"
    return data


def command(guest, line, expected, timeout=15):
    start = len(guest.output)
    send_bytes(guest, line.encode() + b"\r")
    guest.expect(expected, start=start, timeout=timeout)
    guest.expect(b"sup> ", start=start, timeout=timeout)


def main():
    build = ROOT / "build"
    manifest = json.loads((build / "manifest.json").read_text())
    checks = []
    report = {"build_id": manifest["build_id"], "checks": checks, "status": "failed"}
    temporary = tempfile.TemporaryDirectory(prefix="xos_e07_full_")
    disk = Path(temporary.name) / "full.img"
    disk.write_bytes(make_full_image())
    report["disk_bytes"] = disk.stat().st_size
    guest = None
    try:
        guest = Guest(build / "xos.img", "full_disk_boot", work_disk=disk)
        guest.expect(b"xos64> ", timeout=20)
        send_bytes(guest, b"run\r")
        guest.expect(b"sup> ", timeout=20)
        command(guest, "demo keep", b"demo: keep")
        for pid in (1, 3, 4):
            command(guest, f"kill {pid}", b"kill: accepted")
        pump(guest, 0.3)

        start = len(guest.output)
        send_bytes(guest, b"edit note.txt\r")
        guest.expect(b"[edit] note.txt bytes=4 (loaded)", start=start, timeout=12)
        line_start = len(guest.output)
        send_bytes(guest, b"replacement\r")
        guest.expect(b"| ", start=line_start, timeout=10)
        send_bytes(guest, b":wq\r")
        guest.expect(b"[files] save error=", start=start, timeout=15)
        guest.expect(b"[edit] buffer retained", start=start, timeout=10)
        guest.expect(b"| ", start=start, timeout=10)
        send_bytes(guest, b":q!\r")
        guest.expect(b"sup> ", start=start, timeout=10)
        cat_start = len(guest.output)
        send_bytes(guest, b"cat note.txt\r")
        guest.expect(b"old", start=cat_start, timeout=12)
        guest.expect(b"sup> ", start=cat_start, timeout=12)
        cat = bytes(guest.output)[cat_start:]
        if b"replacement" in cat:
            raise AssertionError(f"full-disk save changed old content: {cat[-500:]!r}")
        # A full medium may report no space; mount must not pretend hello was created.
        boot_output = bytes(guest.output)
        if b"[files] ready hello.elf" in boot_output:
            raise AssertionError("full disk unexpectedly created hello.elf")
        checks.append("full_media_save_failure_preserves_old_file")
        report["status"] = "passed"
        print(f"PASS: {len(checks)} E07-full check | build {manifest['build_id']}")
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        if guest is not None:
            guest.close()
        temporary.cleanup()
        (build / "full_disk_smoke_report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
