#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run existing Interactium regressions and the multiwindow damage/owner tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve(); out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    compiler = shutil.which('g++')
    sources = [f'src/user/interactium/{name}.cpp' for name in
               ('window_manager', 'service', 'dispatcher', 'service_loop')]
    report = {'status': 'failed', 'cases': [], 'sanitizers': ['address', 'undefined'],
              'leak_sanitizer': 'disabled: host ptrace prohibits LSan thread enumeration',
              'compiler': subprocess.check_output([compiler, '--version'], text=True).splitlines()[0]}
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1')
    try:
        for name in ('interactium_model_test', 'interactium_transport_test',
                     'interactium_demo_host_test', 'mobius_multiwindow_host'):
            command = [compiler, '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wconversion', '-Wshadow',
                       '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                       '-I', str(ROOT / 'src/shared/include'), '-I', str(ROOT / 'src/user/include'),
                       str(ROOT / 'tests' / (name + '.cpp')), *[str(ROOT / p) for p in sources],
                       '-o', str(out / name)]
            with (out / (name + '.log')).open('w') as log:
                subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
                subprocess.run([str(out / name)], check=True, stdout=log, stderr=subprocess.STDOUT, env=env)
            report['cases'].append({'case': name, 'status': 'passed'})
        report['status'] = 'passed'
        tracked = sources + [f'tests/{case["case"]}.cpp' for case in report['cases']]
        report['sources'] = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in tracked}
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS Mobius host:', len(report['cases']), 'suites')


if __name__ == '__main__':
    main()
