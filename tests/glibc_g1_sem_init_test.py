#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Test patched upstream sem_init failure and private initialization."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
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
with tempfile.TemporaryDirectory(prefix='xos_glibc_sem_') as tmp:
    tmp = Path(tmp)
    (tmp/'nptl').mkdir()
    with tarfile.open(args.archive) as tar:
        item = tar.extractfile('glibc-' + lock['version'] + '/nptl/sem_init.c')
        assert item is not None
        (tmp/'nptl/sem_init.c').write_bytes(item.read())
    subprocess.run(['patch', '-s', '-p1', '-i', str(root/'src/ports/glibc/patches/0010-sem-init-private-only.patch')], cwd=tmp, check=True)
    shutil.copyfile(fixtures/'sem_mock/semaphoreP.h', tmp/'nptl/semaphoreP.h')
    exe = tmp/'test'
    subprocess.run(['clang', '-std=c11', '-Wall', '-Werror', '-I', str(fixtures/'sem_mock'),
                    '-I', str(overlay), str(tmp/'nptl/sem_init.c'), str(fixtures/'sem_init_test.c'),
                    '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print('PASS private sem_init and explicit shared/overflow failure')
