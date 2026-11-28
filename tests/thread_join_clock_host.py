#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check actual libc wrappers' overflow, deadline conversion and error boundaries."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / 'src/ports/glibc/sysdeps/xos'


def main():
    with tempfile.TemporaryDirectory(prefix='xos_join_clock_host_') as directory:
        work = Path(directory)
        (work / 'pthreadP.h').write_text('''#pragma once
#include <pthread.h>
#include <stdbool.h>
#include <stddef.h>
#include <time.h>
#define __timespec64 timespec
#define valid_nanoseconds(n) ((n) >= 0 && (n) < 1000000000)
void __pthread_testcancel(void);
''')
        (work / 'shlib-compat.h').write_text('''#define versioned_symbol(a,b,c,d)
#define libc_hidden_def(x)
#define __set_errno(e) (errno=(e))
''')
        executable = work / 'probe'
        command = [os.environ.get('CC', 'cc'), '-std=gnu11', '-D_GNU_SOURCE', '-O2', '-g',
                   '-Wall', '-Wextra', '-Werror', '-fsanitize=undefined', '-fno-sanitize-recover=all',
                   '-DXOS_GLIBC_IDENTITY_TEST', '-DXOS_GLIBC_CLOCK_TEST',
                   '-DXOS_GLIBC_THREAD_EXTENSIONS_TEST', '-I', str(work), '-I', str(OVERLAY)]
        command.extend(str(OVERLAY / (name + '.c')) for name in (
            'pthread_join_common', 'pthread_tryjoin', 'pthread_getcpuclockid', 'clock_gettime', 'clock_getres'))
        command += [str(ROOT / 'tests/fixtures/glibc_g3/thread_join_clock_host.c'), '-o', str(executable)]
        subprocess.run(command, check=True)
        subprocess.run([executable], check=True, timeout=20)
    print('PASS join/target-clock actual wrappers: overflow, errors, outputs, preemption skew, early-timeout retry and unchanged legacy call')


if __name__ == '__main__':
    main()
