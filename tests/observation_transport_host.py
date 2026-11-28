#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the production observation endpoint against deterministic host transport.

The kernel, clock and authenticated-peer query are explicit fixture substitutes.
This test covers server/client logic and never claims native or guest evidence.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    sources = [Path(__file__), root / 'tests/fixtures/observation_transport_host.cpp',
               root / 'src/user/observation/endpoint.cpp',
               root / 'src/user/include/xos/observation.hpp',
               root / 'src/user/include/xos/sdk.hpp',
               root / 'src/shared/include/xos/observation_service_abi.hpp',
               root / 'src/shared/include/xos/observation_abi.hpp']

    def identities():
        return {path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
                for path in sources}

    report = {'status': 'failed', 'scope': 'production endpoint with host transport substitutes',
              'guest': 'not_run', 'source_sha256': identities(),
              'sanitizers': ['address', 'undefined'] if args.sanitize else []}
    with tempfile.TemporaryDirectory(prefix='xos_observation_transport_') as temporary:
        output = args.output.resolve() if args.output else Path(temporary)
        output.mkdir(parents=True, exist_ok=True)
        binary = output / 'observation_transport_host'
        command = [os.environ.get('CXX', 'c++'), '-std=c++20', '-Wall', '-Wextra', '-Werror',
                   '-I', str(root / 'src/user/include'), '-I', str(root / 'src/shared/include'),
                   str(sources[1]), str(sources[2]), '-o', str(binary)]
        if args.sanitize:
            command[1:1] = ['-O1', '-g', '-fsanitize=address,undefined',
                            '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        try:
            compiled = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            (output / 'compile.log').write_text(compiled.stdout)
            if compiled.returncode:
                print(compiled.stdout, end='')
                raise RuntimeError('observation transport host compilation failed')
            environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:abort_on_error=1')
            run = subprocess.run([str(binary)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, env=environment, timeout=30)
            (output / 'host.log').write_text(run.stdout)
            print(run.stdout, end='')
            report['returncode'] = run.returncode
            report['checks'] = run.stdout.splitlines()
            if run.returncode:
                raise RuntimeError('observation transport host fixture failed')
            if identities() != report['source_sha256']:
                raise RuntimeError('implementation changed during host verification')
            report['status'] = 'passed'
        finally:
            (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
