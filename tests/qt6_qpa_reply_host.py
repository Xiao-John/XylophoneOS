#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the production QPA reply decoder with real Interactium replies."""
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
    output = args.output.resolve()
    output.relative_to(ROOT / 'build')
    output.mkdir(parents=True, exist_ok=False)
    compiler = Path(shutil.which(os.environ.get('CXX', 'g++'))).resolve(strict=True)
    units = ['tests/qt6_qpa_reply_host_test.cpp', 'src/user/interactium/dispatcher.cpp',
             'src/user/interactium/service.cpp', 'src/user/interactium/window_manager.cpp']
    sources = [*units, 'tests/qt6_qpa_reply_host.py', 'src/ports/qt6/qpa/interactium_reply.hpp',
               'src/ports/qt6/qpa/qxos.cpp', 'src/user/interactium/dispatcher.hpp',
               'src/user/interactium/service.hpp', 'src/user/interactium/window_manager.hpp',
               'src/shared/include/xos/interactium_abi.hpp', 'src/shared/include/xos/process_abi.hpp',
               'src/shared/include/xos/display_abi.hpp', 'src/shared/include/xos/abi_types.hpp']
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    hashes = lambda: {path: sha(ROOT / path) for path in sources}
    report = {'status': 'failed', 'scope': 'production QPA decoder; production transport-neutral '
              'Interactium replies; actual heap and stack buffer boundaries',
              'guest': 'not_run', 'full_qt_plugin': 'not_built_by_this_host_gate',
              'sources': hashes(), 'compiler': {'path': str(compiler), 'sha256': sha(compiler),
              'version': subprocess.check_output([compiler, '--version'], text=True)},
              'commands': [], 'results': []}
    try:
        for kind in ('ordinary', 'sanitized'):
            binary = output / kind
            command = [str(compiler), '-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                       '-Wconversion', '-Wshadow', '-I', str(ROOT / 'src/shared/include'),
                       *[str(ROOT / path) for path in units], '-o', str(binary)]
            if kind == 'sanitized':
                command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                            '-fno-sanitize-recover=all']
            report['commands'].append(command)
            with (output / (kind + '_compile.log')).open('w') as stream:
                subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
            environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:abort_on_error=1',
                               UBSAN_OPTIONS='halt_on_error=1')
            run = subprocess.run([str(binary)], capture_output=True, text=True, env=environment, timeout=30)
            log = output / (kind + '.log')
            log.write_text(run.stdout + run.stderr)
            cases = [line.removeprefix('PASS qpa reply case=') for line in run.stdout.splitlines()
                     if line.startswith('PASS qpa reply case=')]
            report['results'].append({'kind': kind, 'returncode': run.returncode, 'cases': cases,
                                      'log_sha256': sha(log), 'binary_sha256': sha(binary)})
            if run.returncode != 0 or len(cases) != 32 or len(set(cases)) != 32 or \
                    'PASS qpa reply total=32' not in run.stdout.splitlines() or run.stderr:
                raise RuntimeError(kind + ' production QPA reply regression failed; see ' + log.name)
            print(kind + ': 32 production decoder cases passed')
        if report['sources'] != hashes():
            raise RuntimeError('production or test sources changed during the gate')
        report['status'] = 'passed'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
