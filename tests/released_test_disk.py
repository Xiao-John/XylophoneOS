# SPDX-License-Identifier: Apache-2.0
"""Read a pinned release archive into a new private guest-test work disk."""
import hashlib
from pathlib import Path
import re
import struct
import tarfile

from work_disk import transfer

ARCHIVE_SHA256 = 'a800969aaed03c601b8eb5029da8df1f4faecc5fa7f66ede28482aa65c7be25a'
WORK_DISK_MEMBER = 'xylophoneos_revival_0.0.1-1024_images/work_disk.img'
WORK_DISK_BYTES = 2 * 1024 * 1024 * 1024


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def prepare_release_disk(archive_path, destination):
    archive_path = Path(archive_path).resolve(strict=True)
    destination = Path(destination)
    archive_sha256 = sha256(archive_path)
    if archive_sha256 != ARCHIVE_SHA256:
        raise AssertionError(f'release images archive SHA256 mismatch: {archive_sha256} != {ARCHIVE_SHA256}')
    digest = hashlib.sha256()
    written = 0
    with tarfile.open(archive_path, 'r:gz') as archive:
        members = [member for member in archive.getmembers() if member.name == WORK_DISK_MEMBER]
        if len(members) != 1 or not members[0].isfile() or members[0].size != WORK_DISK_BYTES:
            raise AssertionError('release images archive lacks the exact regular 2 GiB work disk member')
        # Exclusive creation prevents replacing any existing disk or symlink.
        with archive.extractfile(members[0]) as source, destination.open('xb') as output:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                output.write(block)
                digest.update(block)
                written += len(block)
    if written != WORK_DISK_BYTES or sha256(archive_path) != ARCHIVE_SHA256:
        raise AssertionError('release disk extraction truncated or source archive changed')
    return {'mode': 'released_private_copy', 'release_archive': str(archive_path),
            'release_archive_sha256': ARCHIVE_SHA256, 'member': WORK_DISK_MEMBER,
            'initial_disk_bytes': written, 'initial_disk_sha256': digest.hexdigest()}


def ensure_directory(disk, path):
    """Idempotently ensure the simple root directories used by these tests.

    work_disk_host mkdir intentionally fails on FR_EXIST. Inspect FAT32 root
    metadata read-only first; do not swallow errors or mistake a file for a
    directory. Long names and nested paths are outside this helper's scope.
    """
    if not re.fullmatch(r'/[A-Za-z0-9_]{1,8}', path):
        raise ValueError('test directory helper requires a root 8.3 directory name')
    wanted = path[1:].upper().encode().ljust(11, b' ')
    disk = Path(disk)
    if disk.is_symlink() or not disk.is_file():
        raise ValueError('test disk must be a regular image, not a symlink')
    with disk.open('rb') as stream:
        boot = stream.read(512)
        if len(boot) != 512 or boot[510:] != b'\x55\xaa' or boot[82:90] != b'FAT32   ':
            raise ValueError('test directory helper requires a FAT32 superfloppy')
        sector_size = struct.unpack_from('<H', boot, 11)[0]
        cluster_sectors, fats = boot[13], boot[16]
        reserved = struct.unpack_from('<H', boot, 14)[0]
        fat_sectors = struct.unpack_from('<I', boot, 36)[0]
        cluster = struct.unpack_from('<I', boot, 44)[0]
        total = struct.unpack_from('<I', boot, 32)[0]
        data_sector = reserved + fats * fat_sectors
        if sector_size != 512 or not cluster_sectors or not fat_sectors or total * 512 != disk.stat().st_size:
            raise ValueError('invalid FAT32 test disk geometry')
        max_cluster = (total - data_sector) // cluster_sectors + 1
        seen = set()
        while cluster < 0x0ffffff8:
            if not 2 <= cluster <= max_cluster or cluster in seen:
                raise ValueError('invalid FAT32 root directory chain')
            seen.add(cluster)
            stream.seek((data_sector + (cluster - 2) * cluster_sectors) * 512)
            entries = stream.read(cluster_sectors * 512)
            if len(entries) != cluster_sectors * 512:
                raise ValueError('truncated FAT32 root directory')
            for offset in range(0, len(entries), 32):
                entry = entries[offset:offset + 32]
                if entry[0] == 0:
                    break
                if entry[0] == 0xe5 or entry[11] == 0x0f:
                    continue
                if entry[:11] == wanted:
                    if entry[11] & 0x10 and not entry[11] & 0x08:
                        return
                    raise ValueError(f'test directory path exists as a non-directory: {path}')
            else:
                stream.seek(reserved * 512 + cluster * 4)
                next_cluster = stream.read(4)
                if len(next_cluster) != 4:
                    raise ValueError('truncated FAT32 allocation table')
                cluster = struct.unpack('<I', next_cluster)[0] & 0x0fffffff
                continue
            break
    transfer(disk, 'mkdir', path)
