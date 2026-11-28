#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Production launch controller tested at the modeled kernel trap boundary."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CASES = ('registration', 'authentication', 'malformed_reserved', 'malformed_nonce', 'malformed_pid',
         'initial_timeout', 'callback_timeout', 'revocation', 'failure', 'stale_allow', 'stale_cancel',
         'backpressure', 'wait_pump', 'early_completion', 'fork_lock')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    inputs = [ROOT / 'src/user/sdk/launch_control.cpp', ROOT / 'tests/fixtures/launch_control_host.cpp', Path(__file__)]
    inputs += [path for directory in ('src/shared/include/xos', 'src/user/include/xos')
               for path in (ROOT / directory).glob('*') if path.suffix in ('.h', '.hpp')]
    hashes = lambda: {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    report = {'status': 'failed', 'scope': 'production controller; modeled kernel trap boundary',
              'guest': 'not_run', 'sources': hashes(), 'commands': [], 'results': []}
    try:
        for kind in ('ordinary', 'sanitized'):
            binary = out / kind
            command = [os.environ.get('CXX', 'g++'), '-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                       '-Wconversion', '-Wshadow', '-I', str(ROOT / 'src/shared/include'),
                       '-I', str(ROOT / 'src/user/include'), str(inputs[0]), str(inputs[1]), '-o', str(binary)]
            if kind == 'sanitized':
                command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
            report['commands'].append(command)
            with (out / (kind + '_compile.log')).open('w') as stream:
                subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
            for case in CASES:
                environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:abort_on_error=1', UBSAN_OPTIONS='halt_on_error=1')
                run = subprocess.run([str(binary), case], capture_output=True, text=True, env=environment, timeout=10)
                (out / (kind + '_' + case + '.log')).write_text(run.stdout + run.stderr)
                report['results'].append({'kind': kind, 'case': case, 'returncode': run.returncode})
                if run.returncode or 'PASS launch-control host ' + case not in run.stdout:
                    raise RuntimeError(kind + ' ' + case + ' failed')
                print(run.stdout.strip())
        if report['sources'] != hashes():
            raise ValueError('source changed during test')
        report['status'] = 'passed'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
