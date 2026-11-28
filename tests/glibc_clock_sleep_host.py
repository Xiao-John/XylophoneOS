#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check real clock_nanosleep code against deterministic native clock failures."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='xos_clock_sleep_') as temporary:
    out = Path(temporary)
    (out / 'shlib-compat.h').write_text(
        '#define libc_hidden_def(x)\n#define versioned_symbol(a,b,c,d)\n')
    for name, flags in [('ordinary', []), ('ubsan', ['-fsanitize=undefined', '-fno-sanitize-recover=all'])]:
        binary = out / name
        subprocess.run(['cc', '-std=c11', '-D_POSIX_C_SOURCE=200809L',
                        '-DXOS_GLIBC_CLOCK_TEST', '-Wall', '-Wextra', '-Werror',
                        *flags, '-I', str(out), '-I', str(ROOT / 'src/ports/glibc/sysdeps/xos'),
                        str(ROOT / 'src/ports/glibc/sysdeps/xos/clock_nanosleep.c'),
                        str(ROOT / 'tests/fixtures/glibc_timers/clock_sleep_host.c'),
                        '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
