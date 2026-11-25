#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check unsupported pthread cancellation returns an error without side effects."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'src/ports/glibc/sysdeps/xos/pthread_cancel.c'
fixture = root / 'tests/fixtures/glibc_g1/pthread_cancel_test.c'
with tempfile.TemporaryDirectory(prefix='xos_glibc_pthread_cancel_') as directory:
    temp = Path(directory)
    (temp / 'shlib-compat.h').write_text('#define versioned_symbol(a,b,c,d)\n')
    executable = temp / 'test'
    subprocess.run(['clang', '-std=c11', '-Wall', '-Werror', '-I', str(temp),
                    str(source), str(fixture), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
print('PASS unsupported pthread_cancel returns ENOTSUP without changing errno')
