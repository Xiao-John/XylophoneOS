#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the XOS thread-name registry and public error boundaries."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
overlay = root / 'src/ports/glibc/sysdeps/xos'
fixture = root / 'tests/fixtures/glibc_g1/thread_name_test.c'
with tempfile.TemporaryDirectory(prefix='xos_glibc_thread_name_') as directory:
    tmp = Path(directory)
    (tmp / 'pthreadP.h').write_text(
        '#include <stddef.h>\ntypedef unsigned long pthread_t;\n'
        'pthread_t __pthread_self (void);\nsize_t __strnlen (const char *, size_t);\n')
    (tmp / 'lowlevellock.h').write_text(
        '#include <assert.h>\n#define LLL_PRIVATE 0\n'
        '#define lll_lock(word, kind) assert (__atomic_exchange_n (&(word), 1, __ATOMIC_ACQUIRE) == 0)\n'
        '#define lll_unlock(word, kind) assert (__atomic_exchange_n (&(word), 0, __ATOMIC_RELEASE) == 1)\n')
    (tmp / 'shlib-compat.h').write_text('#define versioned_symbol(lib, internal, public, version)\n')
    executable = tmp / 'test'
    subprocess.run(['clang', '-std=c11', '-Wall', '-Werror', '-I', tmp, '-I', overlay,
                    overlay / 'xos_thread_name.c', overlay / 'pthread_getname.c',
                    overlay / 'pthread_setname.c', fixture, '-o', executable], check=True)
    subprocess.run([executable], check=True)
print('PASS thread names, inheritance, capacity and stale TIDs')
