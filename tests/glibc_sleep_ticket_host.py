#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the production sleep table and native error paths deterministically."""
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
    (out / 'shlib-compat.h').write_text(
        '#define versioned_symbol(lib,impl,name,version) '
        'extern __typeof(impl) name __attribute__((alias(#impl)))\n')
    sources = [ROOT / 'src/ports/glibc/sysdeps/xos/xos_sleep.c',
               ROOT / 'tests/fixtures/glibc_timers/sleep_ticket_host.c']
    report = {'status': 'failed', 'checks': [],
              'leak_sanitizer': 'not_run: host ptrace restriction; target resources checked separately',
              'source_sha256': {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sources}}
    try:
        for name, flags in [('ordinary', []), ('asan_ubsan', [
            '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer'])]:
            binary = out / name
            command = ['cc', '-std=c11', '-D_POSIX_C_SOURCE=200809L',
                       '-DXOS_GLIBC_CLOCK_TEST', '-DXOS_GLIBC_IDENTITY_TEST',
                       '-Wall', '-Wextra', '-Werror', '-g', *flags,
                       '-I', str(out), '-I', str(ROOT / 'src/ports/glibc/sysdeps/xos'),
                       *map(str, sources), '-o', str(binary)]
            subprocess.run(command, check=True)
            environment = dict(os.environ)
            environment['ASAN_OPTIONS'] = 'detect_leaks=0'
            result = subprocess.run([str(binary)], env=environment, text=True, capture_output=True)
            (out / (name + '.log')).write_text(result.stdout + result.stderr)
            result.check_returncode()
            report['checks'].append({'mode': name, 'status': 'passed', 'output': result.stdout.strip()})
        report['status'] = 'passed'
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
