#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the actual glibc Net2 bridge against an injected IPC/FD boundary."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / 'src/ports/glibc/sysdeps/xos'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    sources = [PORT / 'xos_net2_socket.c', ROOT / 'tests/fixtures/glibc_net2/socket_host.c']
    inputs = [*sources, *PORT.glob('*.h'), Path(__file__).resolve()]
    snapshot = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    flags = ['-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-DXOS_GLIBC_FILE_TEST', '-I', str(PORT)]
    if args.sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-pie', '-no-pie']
    with tempfile.TemporaryDirectory(prefix='xos_net2_socket_host_') as temporary:
        binary = Path(temporary) / 'bridge'
        subprocess.run([os.environ.get('CC', 'cc'), *flags, *map(str, sources), '-o', str(binary)], check=True)
        result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
        print(result.stdout, end='')
    if snapshot != {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}:
        raise ValueError('inputs changed while running')
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({'status': 'passed', 'sanitizers': args.sanitize,
            'guest': 'not_run', 'asan_options': os.environ.get('ASAN_OPTIONS', ''),
            'inputs': snapshot, 'stdout': result.stdout}, indent=2) + '\n')


if __name__ == '__main__':
    main()
