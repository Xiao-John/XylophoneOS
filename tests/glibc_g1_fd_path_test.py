#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Test that the unimplemented descriptor-to-path operation fails explicitly."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
overlay = root / 'src/ports/glibc/sysdeps/xos'
fixture = root / 'tests/fixtures/glibc_g1/fd_to_filename_test.c'
with tempfile.TemporaryDirectory(prefix='xos_glibc_fd_path_') as directory:
    executable = Path(directory) / 'test'
    subprocess.run(['clang', '-std=c11', '-Wall', '-Werror', '-I', str(overlay),
                    str(overlay / 'fd_to_filename.c'), str(fixture), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
print('PASS unsupported descriptor-to-path returns ENOTSUP')
