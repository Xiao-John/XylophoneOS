#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check XOS IDs are returned exactly or rejected without truncation."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='xos_glibc_getpid_') as tmp:
    tmp = Path(tmp)
    (tmp/'unistd.h').write_text('typedef int pid_t;\n#define __set_errno(x) (errno=(x))\n#define libc_hidden_def(x)\n#define libc_hidden_weak(x)\n#define weak_alias(a,b)\n')
    exe = tmp/'test'
    subprocess.run(['clang', '-std=c11', '-Wall', '-Werror', '-DXOS_GLIBC_GETPID_TEST', '-I', str(tmp),
                    str(root/'src/ports/glibc/sysdeps/xos/getpid.c'),
                    str(root/'tests/fixtures/glibc_g1/getpid_test.c'), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print('PASS getpid exact representation, overflow and failure')
