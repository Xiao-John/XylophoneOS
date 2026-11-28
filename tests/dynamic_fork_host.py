#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the production fork adapter with modeled native/control boundaries."""
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
    out = args.output.resolve(); out.relative_to(ROOT / 'build'); out.mkdir(parents=True, exist_ok=False)
    names = ['tests/dynamic_fork_host.py', 'tests/fixtures/dynamic_fork_host.cpp',
             'src/user/loader/dynamic/spawn.cpp', 'src/user/loader/dynamic/startup.hpp']
    names += [p.relative_to(ROOT).as_posix() for directory in ('src/shared/include/xos', 'src/user/include/xos')
              for p in sorted((ROOT / directory).glob('*')) if p.suffix in ('.h', '.hpp')]
    hashes = lambda: {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}
    report = {'status': 'failed', 'scope': 'production fork adapter, modeled kernel and policy/control calls',
              'guest': 'not_run', 'sources': hashes(), 'results': []}
    try:
        for mode, options in [('ordinary', []), ('asan_ubsan', ['-fsanitize=address,undefined', '-fno-sanitize-recover=all'])]:
            binary = out / mode
            command = ['g++', '-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wconversion', '-Wshadow',
                       '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections', *options,
                       '-I', str(ROOT / 'src/user/include'), '-I', str(ROOT / 'src/shared/include'),
                       str(ROOT / 'tests/fixtures/dynamic_fork_host.cpp'), '-o', str(binary)]
            with (out / (mode + '_compile.log')).open('w') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20,
                                 env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0:abort_on_error=1'))
            (out / (mode + '.log')).write_text(run.stdout + run.stderr)
            report['results'].append({'mode': mode, 'returncode': run.returncode, 'output': run.stdout})
            run.check_returncode()
            assert 'DYNAMIC_FORK_HOST_PASS' in run.stdout
        assert hashes() == report['sources']
        report['status'] = 'passed'
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS dynamic fork adapter ordinary and ASan/UBSan')


if __name__ == '__main__':
    main()
