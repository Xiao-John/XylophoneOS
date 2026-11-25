#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check that unavailable rseq never reports registration success."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
overlay = root / 'src/ports/glibc/sysdeps/xos'
fixture = root / 'tests/fixtures/glibc_g1/rseq_disabled_test.c'
with tempfile.TemporaryDirectory(prefix='xos_glibc_rseq_') as directory:
    executable = Path(directory) / 'test'
    subprocess.run(['clang', '-std=c11', '-Wall', '-Werror', '-I', str(overlay),
                    str(fixture), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
    unknown = subprocess.run(['clang', '-std=c11', '-Werror', '-I', str(overlay),
                              '-x', 'c', '-c', '-', '-o', str(Path(directory) / 'unknown.o')],
                             input='#include <rseq-internal.h>\nint x = RSEQ_GETMEM_ONCE(flags);\n',
                             text=True, capture_output=True)
    assert unknown.returncode != 0 and 'XOS_RSEQ_UNAVAILABLE_flags' in unknown.stderr
print('PASS unavailable rseq never claims registration')
