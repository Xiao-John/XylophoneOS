#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the actual sys51 dispatch branch and fork admission policy."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

from kernel_process_wait_race_test import definition

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'src/kernel/arch/x86_64/tasks.cpp')
    args = parser.parse_args()
    source = args.source.read_text()
    body = definition(source, 'case sys_process_begin_exit: {')
    fork_admission = definition(source, 'bool fork_admission_open(')
    for signature in ('i64 prepare_fork(', 'case sys_process_fork_commit: {'):
        gate = definition(source, signature)
        if '!fork_admission_open(*current)' not in gate:
            raise AssertionError('fork path must check parent admission: ' + signature)
    dispatch = ('i64 dispatch(u64 first, u64 second = 0) {\n'
                'i64 result = process_error_invalid;\n'
                'switch (sys_process_begin_exit) {\n' + body + '}\nreturn result;\n}\n')
    with tempfile.TemporaryDirectory(prefix='xos_exit_cleanup_') as folder:
        folder = Path(folder)
        (folder / 'exit_cleanup_dispatch.inc').write_text(fork_admission + dispatch)
        executable = folder / 'kernel_exit_cleanup_gate_test'
        subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++20', '-Wall', '-Wextra', '-Werror',
                        '-I', str(folder), '-I', str(ROOT / 'src/shared/include'),
                        str(ROOT / 'tests/kernel_exit_cleanup_gate_test.cpp'), '-o', str(executable)], check=True)
        subprocess.run([str(executable)], check=True)


if __name__ == '__main__':
    main()
