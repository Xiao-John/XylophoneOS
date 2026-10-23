"""Create/format the explicit XOS work disk (FAT16, 16 MiB). Never implicit."""
import argparse
import os
import struct
import sys
from pathlib import Path

SECTOR = 512
SECTORS_PER_CLUSTER = 8
RESERVED = 1
FATS = 2
ROOT_ENTRIES = 512
TOTAL_SECTORS = 16 * 1024 * 1024 // SECTOR
FAT_SECTORS = 16
ROOT_SECTORS = ROOT_ENTRIES * 32 // SECTOR
DATA_START = RESERVED + FATS * FAT_SECTORS + ROOT_SECTORS


def make_image(size=16 * 1024 * 1024):
    total = size // SECTOR
    if total > 0xFFFF:
        raise SystemExit("image too large for FAT16 total16 field")
    image = bytearray(size)
    boot = bytearray(SECTOR)
    boot[0:3] = b"\xeb\x3c\x90"
    boot[3:11] = b"XOS     "
    struct.pack_into("<H", boot, 11, SECTOR)
    boot[13] = SECTORS_PER_CLUSTER
    struct.pack_into("<H", boot, 14, RESERVED)
    boot[16] = FATS
    struct.pack_into("<H", boot, 17, ROOT_ENTRIES)
    struct.pack_into("<H", boot, 19, total)
    boot[21] = 0xF8
    struct.pack_into("<H", boot, 22, FAT_SECTORS)
    struct.pack_into("<H", boot, 24, 32)
    struct.pack_into("<H", boot, 26, 64)
    struct.pack_into("<I", boot, 28, 0)
    struct.pack_into("<I", boot, 32, 0)
    boot[36] = 0x80
    boot[38] = 0x29
    struct.pack_into("<I", boot, 39, 0x584F5331)
    boot[43:54] = b"XOSWORK    "
    boot[54:62] = b"FAT16   "
    boot[510:512] = b"\x55\xaa"
    image[0:SECTOR] = boot
    fat = bytearray(FAT_SECTORS * SECTOR)
    struct.pack_into("<H", fat, 0, 0xFFF8)
    struct.pack_into("<H", fat, 2, 0xFFFF)
    for index in range(FATS):
        offset = (RESERVED + index * FAT_SECTORS) * SECTOR
        image[offset:offset + len(fat)] = fat
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", nargs="?", default="work_disk.img")
    parser.add_argument("--force", action="store_true", help="overwrite and format an existing image")
    parser.add_argument("--size-mib", type=int, default=16)
    args = parser.parse_args()
    path = Path(args.image)
    if path.exists() and not args.force:
        print(f"Work disk exists: {path} ({path.stat().st_size} bytes); not changing it")
        return
    if path.exists() and args.force:
        path.unlink()
    data = make_image(args.size_mib * 1024 * 1024)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)
    print(f"Created FAT16 work disk: {path} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
