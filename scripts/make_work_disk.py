# SPDX-License-Identifier: MIT AND Apache-2.0
# Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
"""Create/format the explicit XOS work disk (FAT32, 2 GiB; legacy test FAT16 supported). Never implicit."""
import argparse
import os
import struct
import sys
import tempfile
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


def create_fat32(path, size_mib=2048):
    """Sparse superfloppy. 4 KiB clusters; FAT32 FSInfo and backup boot sectors."""
    if not 512 <= size_mib <= 2048:
        raise ValueError("FAT32 test baseline supports 512..2048 MiB")
    total = size_mib * 1024 * 1024 // 512
    fat_sectors = 1
    while True:
        clusters = (total - 32 - 2 * fat_sectors) // 8
        needed = ((clusters + 2) * 4 + 511) // 512
        if needed <= fat_sectors: break
        fat_sectors = needed
    boot = bytearray(512)
    boot[:3] = b"\xeb\x58\x90"
    boot[3:11] = b"XOS     "
    struct.pack_into("<HBHBHHBHHHII", boot, 11, 512, 8, 32, 2, 0, 0, 0xf8, 0, 32, 64, 0, total)
    struct.pack_into("<IHHIHH", boot, 36, fat_sectors, 0, 0, 2, 1, 6)
    boot[64] = 0x80; boot[66] = 0x29
    struct.pack_into("<I", boot, 67, 0x584f5332)
    boot[71:82] = b"XOSWORK    "; boot[82:90] = b"FAT32   "
    boot[510:] = b"\x55\xaa"
    info = bytearray(512)
    struct.pack_into("<I", info, 0, 0x41615252)
    struct.pack_into("<III", info, 484, 0x61417272, clusters-1, 3)
    struct.pack_into("<I", info, 508, 0xaa550000)
    fat = bytearray(512)
    struct.pack_into("<III", fat, 0, 0x0ffffff8, 0xffffffff, 0x0fffffff)
    with path.open('xb') as out:
        out.truncate(size_mib*1024*1024)
        for sector, data in ((0,boot),(6,boot),(1,info),(7,info),(32,fat),(32+fat_sectors,fat)):
            out.seek(sector*512); out.write(data)
        out.flush(); os.fsync(out.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", nargs="?", default="work_disk.img")
    parser.add_argument("--size-mib", type=int, default=2048)
    args = parser.parse_args()
    path = Path(args.image)
    if path.exists() or path.is_symlink():
        print(f"Work disk exists: {path}; not changing it (use a new path for FAT32)")
        return
    with tempfile.TemporaryDirectory(prefix=".xos_disk_", dir=path.parent) as folder:
        temporary = Path(folder) / "new.img"
        if args.size_mib == 16:
            with temporary.open('xb') as out: out.write(make_image())
        else:
            create_fat32(temporary, args.size_mib)
        # Exclusive destination creation; never replace an existing work disk.
        os.link(temporary, path)
    print(f"Created work disk: {path} ({path.stat().st_size} bytes)")

if __name__ == "__main__": main()
