#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise reserved TLS setup, DTV allocation failure and cleanup ordering."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
overlay = root / 'src/ports/glibc/sysdeps/xos'
fixtures = root / 'tests/fixtures/glibc_g1'
with tempfile.TemporaryDirectory(prefix='xos_glibc_tls_') as temp:
    exe = Path(temp) / 'test'
    subprocess.run(['clang', '-std=c11', '-Wall', '-Werror', '-DXOS_GLIBC_THREAD_TEST',
                    '-I', str(fixtures/'tls_mock'), '-I', str(overlay),
                    str(fixtures/'thread_tls_test.c'), str(overlay/'xos_thread_tls.c'),
                    str(overlay/'xos_thread_create.c'), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
    subprocess.run(['clang', '-std=c11', '-Wall', '-Werror',
                    '-I', str(fixtures/'tls_mock'), '-I', str(overlay),
                    str(fixtures/'static_worker_test.c'), str(overlay/'xos_static_worker.c'),
                    '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print('PASS TLS setup, DTV allocation failure and explicit cleanup')
print('PASS static worker stack handoff, callback ownership and cleanup ordering')
