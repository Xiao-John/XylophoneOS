#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise XOS heap calls and their pre-TLS failure path."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
overlay = root / 'src/ports/glibc/sysdeps/xos'
fixture = root / 'tests/fixtures/glibc_g1/heap_break_test.c'
with tempfile.TemporaryDirectory(prefix='xos_glibc_heap_') as folder:
    tmp = Path(folder)
    (tmp / 'ldsodefs.h').write_text('')
    shims = tmp / 'shims.h'
    shims.write_text('#define __set_errno(value) (errno = (value))\n#define weak_alias(from, to)\n')
    exe = tmp / 'test'
    subprocess.run(['clang', '-std=c11', '-Wall', '-Werror', '-DXOS_GLIBC_HEAP_TEST',
                    '-include', shims, '-I', tmp, '-I', overlay,
                    overlay / 'brk.c', overlay / 'dl-early_allocate.c', fixture,
                    '-o', exe], check=True)
    subprocess.run([exe], check=True)
print('PASS native heap-break results and pre-TLS allocation failure')
