#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify that the ordinary XOS glibc SDK emits thread-safe allocation paths."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-build', type=Path, required=True)
    args = parser.parse_args()
    manifest_path = args.sdk_build / 'manifest.json'
    manifest = json.loads(manifest_path.read_bytes())
    if manifest.get('status') != 'static_sdk_built':
        raise ValueError('a completed glibc SDK is required')
    overlay = 'src/ports/glibc/sysdeps/xos/sysdep-cancel.h'
    if manifest['inputs'].get(overlay) != sha(ROOT / overlay):
        raise ValueError('SDK does not bind the current XOS cancellation header')
    archive_name = 'usr/lib/libc.a'
    archive = args.sdk_build / 'sysroot' / archive_name
    if sha(archive) != manifest['artifacts'][archive_name]:
        raise ValueError('libc.a differs from the SDK manifest')
    tools = {}
    for name in ('x86_64-elf-ar', 'x86_64-elf-objdump'):
        path = shutil.which(name)
        if path is None or sha(path) != manifest['tools'][name]['sha256']:
            raise ValueError(name + ' differs from the SDK build')
        tools[name] = path

    checks = (
        ('malloc.o', '__libc_malloc2', (r'\block\s+cmpxchg\b', r'\b__lll_lock_wait_private\b')),
        ('pthread_mutex_lock.o', '___pthread_mutex_lock', (r'\block\s+cmpxchg\b', r'\b__lll_lock_wait\b')),
        ('pthread_mutex_unlock.o', '__pthread_mutex_unlock_usercnt', (r'\bxchg\b', r'\b__lll_lock_wake\b')),
    )
    with tempfile.TemporaryDirectory(prefix='xos_glibc_allocator_link_') as directory:
        for member, symbol, patterns in checks:
            path = Path(directory) / member
            path.write_bytes(subprocess.check_output([tools['x86_64-elf-ar'], 'p', archive, member]))
            code = subprocess.check_output([tools['x86_64-elf-objdump'], '-dr',
                                            '--disassemble=' + symbol, path], text=True)
            if any(re.search(pattern, code) is None for pattern in patterns):
                raise ValueError('missing threaded lock instructions or slow path in ' + symbol)
    print('PASS glibc allocator and pthread mutex locking are present in SDK libc.a')


if __name__ == '__main__':
    main()
