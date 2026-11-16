#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compare reserved TLS placement with the locked glibc implementation."""
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
overlay = root/'src/ports/glibc/sysdeps/xos'
with tempfile.TemporaryDirectory(prefix='xos_glibc_tls_upstream_') as tmp:
    tmp = Path(tmp)
    with tarfile.open(args.archive) as tar:
        item = tar.extractfile('glibc-' + lock['version'] + '/elf/dl-tls_block_align.h')
        assert item is not None
        (tmp/'dl-tls_block_align.h').write_bytes(item.read())
    exe = tmp/'compare'
    subprocess.run(['clang', '-std=c11', '-Wall', '-Werror', '-DXOS_GLIBC_THREAD_TEST',
                    '-I', str(tmp), '-I', str(overlay),
                    str(root/'tests/fixtures/glibc_g1/tls_upstream_compare.c'),
                    str(overlay/'xos_thread_create.c'), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print('PASS XOS TLS layout matches locked glibc for aligned inputs')
