#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify own-process CPU-clock selection, errors and output preservation."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='xos_self_cpuclock_') as temporary:
    out = Path(temporary)
    (out / 'shim.h').write_text('''
#define _GNU_SOURCE 1
#include <time.h>
#include <unistd.h>
#define __set_errno(value) (errno = (value))
#define weak_alias(a, b)
int __clock_getres(clockid_t, struct timespec *);
pid_t __getpid(void);
''')
    binary = out / 'probe'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-include', str(out / 'shim.h'),
                    str(ROOT / 'src/ports/glibc/sysdeps/xos/clock_getcpuclockid.c'),
                    str(ROOT / 'tests/fixtures/glibc_timers/self_cpuclock_host.c'),
                    '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
