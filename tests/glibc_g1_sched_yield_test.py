#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check sched_yield dispatch and errno contract with a mocked XOS trap."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='xos_glibc_yield_') as tmp:
    tmp = Path(tmp)
    (tmp/'sched.h').write_text('#define libc_hidden_def(x)\n#define weak_alias(a,b)\n')
    exe = tmp/'test'
    subprocess.run(['clang', '-std=c11', '-Wall', '-Werror', '-DXOS_GLIBC_YIELD_TEST', '-I', str(tmp),
                    str(root/'src/ports/glibc/sysdeps/xos/sched_yield.c'),
                    str(root/'tests/fixtures/glibc_g1/sched_yield_test.c'), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print('PASS sched_yield dispatch and errno preservation')
