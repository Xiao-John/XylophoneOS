#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify unsupported cancellation operations fail without issuing a syscall."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
overlay = root / 'src/ports/glibc/sysdeps/xos'
fixture = root / 'tests/fixtures/glibc_g1/cancellation_test.c'
with tempfile.TemporaryDirectory(prefix='xos_glibc_cancel_') as directory:
    temp = Path(directory)
    (temp / 'syscall_types.h').write_text('typedef long int __syscall_arg_t;\n')
    executable = temp / 'test'
    subprocess.run(['clang', '-std=c11', '-Wall', '-Werror', '-I', str(temp),
                    str(overlay / 'cancellation.c'), str(fixture), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
print('PASS unsupported cancellation returns ENOSYS with correct errno convention')
