#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the production native files client with only kernel traps replaced."""
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
    out.mkdir(parents=True, exist_ok=False)
    paths = [ROOT / name for name in ('src/user/sdk/file_client.cpp', 'src/user/sdk/text.cpp',
             'tests/fixtures/dynamic_admission/file_deadline.cpp')]
    headers = [path for directory in ('src/user/include/xos', 'src/shared/include/xos')
               for path in (ROOT / directory).rglob('*.hpp')]
    inputs = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in [*paths, *headers, Path(__file__)]}
    command = [os.environ.get('CXX', 'g++'), '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror',
               '-Wconversion', '-Wshadow', '-ffunction-sections', '-fdata-sections',
               '-I', str(ROOT / 'src/shared/include'), '-I', str(ROOT / 'src/user/include'),
               *map(str, paths), '-Wl,--gc-sections', '-o', str(out / 'test')]
    with (out / 'compile.log').open('w') as stream:
        subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
    results = []
    for case in ('ordinary', 'expired', 'ready', 'timeout', 'legacy_timeout', 'at_deadline',
                 'send_failure', 'closed', 'bad_magic', 'bad_sequence', 'bad_size', 'bad_status', 'bad_length'):
        run = subprocess.run([str(out / 'test'), case], capture_output=True, text=True, timeout=5)
        (out / (case + '.log')).write_text(run.stdout + run.stderr)
        results.append({'case': case, 'returncode': run.returncode})
        if run.returncode:
            raise RuntimeError(case + ' failed')
        print(run.stdout.strip())
    (out / 'report.json').write_text(json.dumps({'status': 'passed', 'scope': 'native client with kernel trap injection',
        'guest': 'not_run', 'command': command, 'inputs': inputs, 'results': results}, indent=2) + '\n')


if __name__ == '__main__':
    main()
