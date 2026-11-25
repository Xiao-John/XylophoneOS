#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise real XOS wait conversion with injected native clock/wait results."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    overlay = root / 'src/ports/glibc/sysdeps/xos'
    with tempfile.TemporaryDirectory(prefix='xos_glibc_g3_wait_') as directory:
        executable = Path(directory) / 'wait_test'
        command = [os.environ.get('CC', 'cc'), '-std=c11', '-O2', '-g',
                   '-Wall', '-Wextra', '-Werror', '-DXOS_GLIBC_CLOCK_TEST',
                   '-I', str(overlay), str(overlay / 'xos_timed_wait.c'),
                   str(overlay / 'xos_lll_futex.c'),
                   str(root / 'tests/fixtures/glibc_g3/timed_wait.c'),
                   '-o', str(executable)]
        if args.sanitize:
            command[1:1] = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        subprocess.run(command, check=True)
        environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1')
        subprocess.run([str(executable)], env=environment, check=True, timeout=20)
    print('PASS G3 private waits: untimed, monotonic/realtime, sampling skew, '
          'clock errors, invalid times, finite overflow, errno preservation')


if __name__ == '__main__':
    main()
