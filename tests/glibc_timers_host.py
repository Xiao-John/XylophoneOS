#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Deterministic production timer tests with controlled clocks and worker reap."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / 'src/ports/glibc/sysdeps/xos'
with tempfile.TemporaryDirectory(prefix='xos_timers_') as temporary:
    out = Path(temporary)
    # Only the glibc private attribute adapter is substituted. The complete
    # production pool, deadlines, scheduler and callback paths run unchanged.
    (out / 'pthreadP.h').write_text('''
#include <pthread.h>
#include <stddef.h>
#include <stdbool.h>
#include <signal.h>
struct pthread_attr_extension { void *cpuset; bool sigmask_set; };
struct pthread_attr {
  int flags; size_t guardsize, stacksize;
  struct pthread_attr_extension *extension;
};
#define ATTR_FLAG_STACKADDR 1
#define ATTR_FLAG_NOTINHERITSCHED 2
#define ATTR_FLAG_SCOPEPROCESS 4
#define ATTR_FLAG_DO_RSEQ 8
int timer_test_attr_init(pthread_attr_t *);
int timer_test_attr_copy(pthread_attr_t *, const pthread_attr_t *);
int timer_test_attr_size(pthread_attr_t *, size_t);
int timer_test_attr_detach(pthread_attr_t *, int);
int timer_test_attr_destroy(pthread_attr_t *);
int timer_test_create(pthread_t *, const pthread_attr_t *, void *(*)(void *), void *);
#define __pthread_attr_init timer_test_attr_init
#define __pthread_attr_copy timer_test_attr_copy
#define __pthread_attr_setstacksize timer_test_attr_size
#define __pthread_attr_setdetachstate timer_test_attr_detach
#define __pthread_attr_destroy timer_test_attr_destroy
#define __pthread_create timer_test_create
#undef pthread_cleanup_push
#undef pthread_cleanup_pop
#define pthread_cleanup_push(fn,arg) do { void (*cleanup)(void *) = (fn); void *cleanup_arg = (arg);
#define pthread_cleanup_pop(run) if (run) cleanup(cleanup_arg); } while (0)
#define __set_errno(value) (errno = (value))
void __libc_fatal(const char *) __attribute__((noreturn));
''')
    (out / 'libc-internal.h').write_text('')
    compiler = os.environ.get('CC', 'cc')
    for kind, flags in [('ordinary', []), ('asan_ubsan',
                                       ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'])]:
        binary = out / kind
        subprocess.run([compiler, '-std=c11', '-D_GNU_SOURCE', '-Wall', '-Wextra', '-Werror',
                        '-g', *flags, '-DXOS_GLIBC_CLOCK_TEST', '-DXOS_GLIBC_IDENTITY_TEST',
                        '-I', str(out), '-I', str(PORT),
                        str(PORT / 'xos_timer.c'),
                        str(ROOT / 'tests/fixtures/glibc_timers/timer_host.c'),
                        '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True,
                       env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
        print('PASS production timer semantics', kind)
