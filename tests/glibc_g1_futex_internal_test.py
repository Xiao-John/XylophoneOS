#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise glibc's XOS timed-wait adapter with explicit failure checks."""
from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
overlay = root / 'src/ports/glibc/sysdeps/xos'
fixture = root / 'tests/fixtures/glibc_g1/futex_internal_test.c'
with tempfile.TemporaryDirectory(prefix='xos_glibc_futex_') as directory:
    temp = Path(directory)
    (temp / 'atomic.h').write_text('/* host test declarations */\n')
    (temp / 'futex-internal.h').write_text('''#include <time.h>
struct __timespec64 { long tv_sec; long tv_nsec; };
#define FUTEX_PRIVATE 0
#define libc_hidden_def(name)
static inline __attribute__((noreturn)) void futex_fatal_error(void) { __builtin_trap(); }
''')
    executable = temp / 'test'
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-D_POSIX_C_SOURCE=200809L', '-Wall', '-Werror',
                    '-I', str(temp), '-I', str(overlay), str(overlay / 'futex-internal.c'),
                    str(fixture), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
print('PASS private monotonic/realtime futex forwarding and unsupported/fatal paths')
