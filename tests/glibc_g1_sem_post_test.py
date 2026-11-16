#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Test patched upstream sem_post with private wake and overflow checks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--archive', type=Path, required=True)
args = parser.parse_args()
lock = json.loads((root/'src/ports/glibc/source_lock.json').read_text())
assert hashlib.sha256(args.archive.read_bytes()).hexdigest() == lock['archive_sha256']
fixtures = root/'tests/fixtures/glibc_g1'
overlay = root/'src/ports/glibc/sysdeps/xos'
with tempfile.TemporaryDirectory(prefix='xos_glibc_sem_post_') as tmp:
    tmp = Path(tmp)
    with tarfile.open(args.archive) as tar:
        for name in ('nptl/sem_post.c', 'sysdeps/nptl/internaltypes.h'):
            member = tar.extractfile('glibc-' + lock['version'] + '/' + name)
            assert member is not None
            path = tmp/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(member.read())
    subprocess.run(['patch', '-s', '-p1', '-i', str(root/'src/ports/glibc/patches/0011-nptl-explicit-includes.patch')], cwd=tmp, check=True)
    exe = tmp/'test'
    subprocess.run(['clang', '-std=c11', '-Wall', '-Werror', '-I', str(fixtures/'sem_post_mock'),
                    '-I', str(fixtures/'sem_mock'), '-I', str(overlay), str(tmp/'nptl/sem_post.c'),
                    str(fixtures/'sem_post_test.c'), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print('PASS sem_post token, overflow and private-wake behavior')
