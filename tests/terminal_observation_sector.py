# SPDX-License-Identifier: Apache-2.0
"""Preallocate offline observation files; read only their fixed data sector live."""
import hashlib
from pathlib import Path
import secrets
import struct

from work_disk import transfer


def observation_record(nonce):
    if len(nonce) != 32 or any(char not in '0123456789abcdef' for char in nonce):
        raise ValueError('observation nonce must be 128-bit lowercase hexadecimal')
    prefix = ('G3_BLOCK_OBSERVATION v=1 before_threads=2 before_waiting=1 '
              'after_threads=2 after_waiting=1 file_progress=1 nonce=' + nonce + '\n').encode() + b'\0'
    return prefix + b'\xa5' * (512 - len(prefix))


def file_sector_offline(disk, name):
    """Resolve one just-created root 8.3 file before QEMU is started."""
    wanted = name[1:].upper().encode().ljust(11, b' ')
    with disk.open('rb') as stream:
        boot = stream.read(512)
        if len(boot) != 512 or boot[510:] != b'\x55\xaa' or boot[82:90] != b'FAT32   ':
            raise ValueError('observation needs the private FAT32 superfloppy')
        bps, spc = struct.unpack_from('<H', boot, 11)[0], boot[13]
        reserved, fats = struct.unpack_from('<H', boot, 14)[0], boot[16]
        fat_sectors, cluster = struct.unpack_from('<I', boot, 36)[0], struct.unpack_from('<I', boot, 44)[0]
        total = struct.unpack_from('<I', boot, 32)[0]
        first = reserved + fats * fat_sectors
        if bps != 512 or not spc or not fat_sectors or total * 512 != disk.stat().st_size:
            raise ValueError('invalid observation disk geometry')
        maximum = (total - first) // spc + 1
        seen = set()
        while cluster < 0x0ffffff8:
            if not 2 <= cluster <= maximum or cluster in seen:
                raise ValueError('invalid root directory chain')
            seen.add(cluster)
            stream.seek((first + (cluster - 2) * spc) * 512)
            block = stream.read(spc * 512)
            if len(block) != spc * 512:
                raise ValueError('short root directory read')
            for at in range(0, len(block), 32):
                entry = block[at:at + 32]
                if entry[0] == 0:
                    raise ValueError('new observation file not found')
                if entry[0] == 0xe5 or entry[11] == 0x0f or entry[:11] != wanted:
                    continue
                if entry[11] & 0x18 or struct.unpack_from('<I', entry, 28)[0] != 512:
                    raise ValueError('observation must be an ordinary 512-byte file')
                target = (struct.unpack_from('<H', entry, 20)[0] << 16) | struct.unpack_from('<H', entry, 26)[0]
                if not 2 <= target <= maximum:
                    raise ValueError('invalid observation cluster')
                stream.seek(reserved * 512 + target * 4)
                if struct.unpack('<I', stream.read(4))[0] & 0x0fffffff < 0x0ffffff8:
                    raise ValueError('observation must occupy one preallocated cluster')
                offset = (first + (target - 2) * spc) * 512
                stream.seek(offset)
                if stream.read(512) != bytes(512):
                    raise ValueError('observation file initial bytes differ')
                return offset
            stream.seek(reserved * 512 + cluster * 4)
            cluster = struct.unpack('<I', stream.read(4))[0] & 0x0fffffff
    raise ValueError('observation file missing from root chain')


def prepare_observations(disk, count):
    """All filesystem operations happen offline; live readers use only offsets."""
    disk = Path(disk)
    seed = disk.with_name('observation_zero.bin')
    seed.write_bytes(bytes(512))
    observations = []
    try:
        for index in range(count):
            path = '/g3obs' + str(index + 1)
            nonce = secrets.token_hex(16)
            transfer(disk, 'import', path, seed)
            offset = file_sector_offline(disk, path)
            observations.append({'path': path, 'nonce': nonce, 'offset': offset,
                                 'expected_sha256': hashlib.sha256(observation_record(nonce)).hexdigest()})
    finally:
        seed.unlink()
    if len({item['nonce'] for item in observations}) != count or len({item['offset'] for item in observations}) != count:
        raise ValueError('observation nonces and sectors must be distinct')
    return observations
