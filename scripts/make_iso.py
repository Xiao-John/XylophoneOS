# SPDX-License-Identifier: Apache-2.0
"""Build a minimal BIOS El Torito ISO whose boot image contains boot+loader+kernel."""

import argparse
import struct
from pathlib import Path

SECTOR = 2048
BOOT_LOAD_SEGMENT = 0
BOOT_RBA = 26
BOOT_CATALOG_RBA = 25


def both16(value):
    return struct.pack('<H', value) + struct.pack('>H', value)


def both32(value):
    return struct.pack('<I', value) + struct.pack('>I', value)


def record(extent, size, flags, name):
    body = bytearray(33 + len(name))
    body[0] = len(body)
    body[1] = 0
    body[2:10] = both32(extent)
    body[10:18] = both32(size)
    body[18:25] = bytes((126, 1, 1, 0, 0, 0, 0))
    body[25] = flags
    body[26] = 0
    body[27] = 0
    body[28:32] = both16(1)
    body[32] = len(name)
    body[33:] = name
    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot', type=Path, required=True)
    parser.add_argument('--loader', type=Path, required=True)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--file', action='append', default=[],
                        metavar='NAME=PATH', help='add a file to the ISO root')
    parser.add_argument('--loader-slot', type=lambda value: int(value, 0),
                        default=0x1000, help='bytes reserved for the boot loader')
    args = parser.parse_args()
    boot = args.boot.read_bytes()
    loader = args.loader.read_bytes()
    kernel = args.kernel.read_bytes()
    if len(boot) != 512:
        raise SystemExit('boot sector must be exactly 512 bytes')
    if len(loader) > 0x1000:
        raise SystemExit('ISO loader exceeds the 4 KiB slot')
    if len(loader) > args.loader_slot:
        raise SystemExit('loader exceeds --loader-slot')
    kernel_offset = 0x400 + args.loader_slot
    blob = bytearray(kernel_offset + len(kernel))
    blob[0:512] = boot
    blob[0x400:0x400 + len(loader)] = loader
    blob[kernel_offset:] = kernel
    if 0x7C00 + len(blob) >= 0xA0000:
        raise SystemExit('ISO boot image would exceed real-mode memory')
    boot_sectors = (len(blob) + 511) // 512
    boot_blocks = (len(blob) + SECTOR - 1) // SECTOR
    root_lba = BOOT_RBA + boot_blocks
    path_lba = root_lba + 1
    files = []
    next_lba = path_lba + 1
    for item in args.file:
        if '=' not in item:
            raise SystemExit('--file requires NAME=PATH')
        name, source = item.split('=', 1)
        data = Path(source).read_bytes()
        blocks = max(1, (len(data) + SECTOR - 1) // SECTOR)
        files.append((name, data, next_lba))
        next_lba += blocks
    total = next_lba
    image = bytearray(total * SECTOR)

    pvd = bytearray(SECTOR)
    pvd[0] = 1
    pvd[1:6] = b'CD001'
    pvd[6] = 1
    pvd[8:40] = b'XOS'.ljust(32)
    pvd[40:72] = b'XOS_ISO'.ljust(32)
    pvd[80:88] = both32(total)
    pvd[120:124] = both16(1)
    pvd[124:128] = both16(1)
    pvd[128:132] = both16(SECTOR)
    pvd[132:140] = both32(10)
    pvd[140:144] = struct.pack('<I', path_lba)
    pvd[148:152] = b'\x00\x00\x00\x00'
    pvd[156:190] = record(root_lba, SECTOR, 2, b'\x00')
    pvd[881] = 1
    image[16 * SECTOR:17 * SECTOR] = pvd

    boot_record = bytearray(SECTOR)
    boot_record[0] = 0
    boot_record[1:6] = b'CD001'
    boot_record[6] = 1
    boot_record[7:39] = b'EL TORITO SPECIFICATION'.ljust(32, b'\x00')
    boot_record[71:75] = struct.pack('<I', BOOT_CATALOG_RBA)
    image[17 * SECTOR:18 * SECTOR] = boot_record

    term = bytearray(SECTOR)
    term[0] = 255
    term[1:6] = b'CD001'
    term[6] = 1
    image[18 * SECTOR:19 * SECTOR] = term

    catalog = bytearray(SECTOR)
    validation = bytearray(32)
    validation[0] = 1
    validation[1] = 0
    validation[4:28] = b'XOS'.ljust(24)
    validation[30:32] = b'\x55\xaa'
    words = struct.unpack('<16H', validation)
    checksum = (-sum(words)) & 0xFFFF
    struct.pack_into('<H', validation, 28, checksum)
    initial = bytearray(32)
    initial[0] = 0x88
    initial[1] = 0
    struct.pack_into('<H', initial, 2, BOOT_LOAD_SEGMENT)
    struct.pack_into('<H', initial, 6, boot_sectors)
    struct.pack_into('<I', initial, 8, BOOT_RBA)
    catalog[0:32] = validation
    catalog[32:64] = initial
    image[BOOT_CATALOG_RBA * SECTOR:(BOOT_CATALOG_RBA + 1) * SECTOR] = catalog

    start = BOOT_RBA * SECTOR
    image[start:start + len(blob)] = blob

    root = bytearray(SECTOR)
    dot = record(root_lba, SECTOR, 2, b'\x00')
    dotdot = record(root_lba, SECTOR, 2, b'\x01')
    pos = 0
    for entry in (dot, dotdot):
        root[pos:pos + len(entry)] = entry
        pos += len(entry)
    for name, data, extent in files:
        entry = record(extent, len(data), 0, (name + ';1').encode('ascii'))
        root[pos:pos + len(entry)] = entry
        pos += len(entry)
    if pos > SECTOR:
        raise SystemExit('ISO root directory exceeds one sector')
    image[root_lba * SECTOR:(root_lba + 1) * SECTOR] = root
    for name, data, extent in files:
        start = extent * SECTOR
        image[start:start + len(data)] = data

    path = bytearray(SECTOR)
    path[0] = 1
    path[1] = 0
    path[2:6] = struct.pack('<I', root_lba)
    path[6:8] = struct.pack('<H', 1)
    path[8:10] = b'\x00\x00'
    image[path_lba * SECTOR:(path_lba + 1) * SECTOR] = path

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(image)
    print(f'ISO {args.output} sectors={total} boot_sectors={boot_sectors} '
          f'boot_bytes={len(blob)} kernel_bytes={len(kernel)}')


if __name__ == '__main__':
    main()
