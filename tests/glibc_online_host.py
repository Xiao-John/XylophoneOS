#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise production online mapping gates and worker DTV retirement on the host."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / 'src/ports/glibc/sysdeps/xos'
FIXTURES = ROOT / 'tests/fixtures/glibc_online'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    inputs = [Path(__file__), *PORT.glob('*.h'), PORT / 'xos_rtld_mapping.c',
              *(PORT / (name + '.c') for name in ('xos_thread_tls', 'xos_static_worker',
                                                  'xos_thread_create', 'xos_thread_exit')),
              *FIXTURES.rglob('*.h'), FIXTURES / 'mapping_host.c', FIXTURES / 'worker_host.c']
    bindings = {str(path.relative_to(ROOT)): sha(path) for path in inputs}
    report = {'status': 'failed', 'guest': 'not_run', 'sources': bindings, 'runs': []}
    cc = os.environ.get('CC', 'cc')
    report['compiler'] = subprocess.check_output([cc, '--version'], text=True).splitlines()[0]
    try:
        for sanitized in (False, True):
            for kind in ('mapping_fixed', 'mapping_online', 'worker_online'):
                name = kind + ('_asan_ubsan' if sanitized else '')
                target = out / name
                flags = ['-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                         '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
                         '-I', str(PORT), '-pthread']
                if sanitized:
                    flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
                if kind == 'worker_online':
                    flags += ['-DSHARED', '-DXOS_ONLINE_CLOSURE', '-DXOS_GLIBC_THREAD_TEST',
                              '-I', str(FIXTURES / 'worker_include')]
                    sources = [FIXTURES / 'worker_host.c',
                               *(PORT / (item + '.c') for item in (
                                   'xos_static_worker', 'xos_thread_tls', 'xos_thread_create', 'xos_thread_exit'))]
                else:
                    flags += ['-DXOS_GLIBC_FILE_TEST']
                    if kind == 'mapping_online':
                        flags += ['-DXOS_ONLINE_CLOSURE']
                    sources = [FIXTURES / 'mapping_host.c', PORT / 'xos_rtld_mapping.c']
                command = [cc, *flags, *map(str, sources), '-o', str(target)]
                with (out / (name + '_compile.log')).open('w') as log:
                    subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
                environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:abort_on_error=1',
                                   UBSAN_OPTIONS='halt_on_error=1')
                run = subprocess.run([target], env=environment, capture_output=True, timeout=20)
                log = out / (name + '.log')
                log.write_bytes(run.stdout + run.stderr)
                report['runs'].append({'name': name, 'returncode': run.returncode,
                                       'command': command, 'log_sha256': sha(log)})
                if run.returncode:
                    raise RuntimeError(name + ' failed; see ' + str(log))
                print(run.stdout.decode().strip(), flush=True)
        if bindings != {str(path.relative_to(ROOT)): sha(path) for path in inputs}:
            raise ValueError('production or fixture inputs changed')
        report['status'] = 'passed'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
