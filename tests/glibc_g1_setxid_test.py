#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify the unsupported XOS credential transition fails without side effects."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'src/ports/glibc/sysdeps/xos/nptl_setxid.c'
fixture = root / 'tests/fixtures/glibc_g1/setxid_test.c'
with tempfile.TemporaryDirectory(prefix='xos_glibc_setxid_') as directory:
    executable = Path(directory) / 'test'
    subprocess.run(['clang', '-std=c11', '-D_POSIX_C_SOURCE=200809L', '-Wall', '-Werror',
                    str(source), str(fixture), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
print('PASS unsupported credential transition and unexpected-handler failure')
