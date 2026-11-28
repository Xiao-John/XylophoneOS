#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check terminal/control preservation against modeled native channel metadata."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    names = ['tests/dynamic_terminal_host.py', 'tests/fixtures/dynamic_terminal_host.cpp',
             'src/user/loader/load.cpp', 'src/user/loader/image_reader.hpp']
    names += [p.relative_to(ROOT).as_posix() for folder in ('src/shared/include/xos', 'src/user/include/xos')
              for p in sorted((ROOT / folder).glob('*')) if p.suffix in ('.h', '.hpp')]
    hashes = lambda: {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}
    report = {'status': 'failed', 'guest': 'not_run', 'scope': 'production preservation validator; modeled metadata',
              'sources': hashes(), 'results': [], 'commands': []}
    try:
        for mode, extra in [('ordinary', []), ('asan_ubsan', ['-fsanitize=address,undefined', '-fno-sanitize-recover=all'])]:
            binary = out / mode
            command = ['g++', '-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                       '-Wconversion', '-Wshadow', '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
                       *extra, '-I', str(ROOT / 'src/user/include'), '-I', str(ROOT / 'src/shared/include'),
                       str(ROOT / 'tests/fixtures/dynamic_terminal_host.cpp'), '-o', str(binary)]
            report['commands'].append(command)
            with (out / (mode + '_compile.log')).open('w') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20,
                                 env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0:abort_on_error=1'))
            (out / (mode + '.log')).write_text(run.stdout + run.stderr)
            report['results'].append({'mode': mode, 'returncode': run.returncode, 'output': run.stdout})
            run.check_returncode()
            if 'DYNAMIC_TERMINAL_HOST_PASS' not in run.stdout:
                raise RuntimeError('missing terminal validation completion marker')
        if hashes() != report['sources']:
            raise ValueError('source changed during host qualification')
        report['status'] = 'passed'
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS dynamic terminal validation ordinary and ASan/UBSan')


if __name__ == '__main__':
    main()
