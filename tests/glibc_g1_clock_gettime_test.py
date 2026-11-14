#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check XOS clock selection, conversion and failure behavior."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='xos_glibc_clock_') as tmp:
    tmp = Path(tmp)
    (tmp/'time.h').write_text('typedef int clockid_t;\nstruct timespec { long tv_sec; long tv_nsec; };\n#define CLOCK_REALTIME 0\n#define CLOCK_MONOTONIC 1\n#define CLOCK_PROCESS_CPUTIME_ID 2\n#define CLOCK_THREAD_CPUTIME_ID 3\n')
    (tmp/'shlib-compat.h').write_text('#define __set_errno(x) (errno=(x))\n#define libc_hidden_def(x)\n#define versioned_symbol(a,b,c,d)\n')
    exe = tmp/'test'
    subprocess.run(['clang', '-std=c11', '-Wall', '-Werror', '-DXOS_GLIBC_CLOCK_TEST', '-I', str(tmp), '-I', str(root/'src/ports/glibc/sysdeps/xos'),
                    str(root/'src/ports/glibc/sysdeps/xos/clock_gettime.c'),
                    str(root/'tests/fixtures/glibc_g1/clock_gettime_test.c'), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
    subprocess.run(['clang++', '-std=c++17', '-Wall', '-Werror',
                    '-I', str(root/'src/shared/include'), '-I', str(root/'src/ports/glibc/sysdeps/xos'),
                    str(root/'tests/fixtures/glibc_g1/cpu_time_abi_test.cpp'), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print('PASS clock selection, ns conversion and explicit failures')
