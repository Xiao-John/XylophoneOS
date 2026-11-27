#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify glibc terminal FD/termios/native-client behavior with kernel traps substituted."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CASES = ['basic', 'v3', 'lease', 'concurrent', 'invalid_v2', 'invalid_v3',
         'missing_flag', 'missing_object', 'zero_sequence', 'bad_peer', 'bad_rights',
         'bad_controller', 'duplicate_channels', 'wrong_sequence', 'reserved',
         'unknown_status', 'bad_mode', 'overread', 'zero_write', 'short_reply',
         'service_death', 'timeout', 'interrupted', 'readiness',
         'fork_ok', 'fork_terminal_timeout', 'fork_files_timeout']


def compiled_sources():
    overlay = ROOT / 'src/ports/glibc/sysdeps/xos'
    return [overlay / (name + '.c') for name in
            ('xos_file_runtime', 'xos_file_session', 'xos_net2_socket', 'xos_terminal_runtime', 'ioctl', 'select')] + [
        ROOT / 'src/ports/glibc/terminal_support.cpp', ROOT / 'src/user/sdk/terminal_client.cpp',
        ROOT / 'tests/fixtures/glibc_g3/terminal_runtime.cpp']


def source_snapshot():
    overlay = ROOT / 'src/ports/glibc/sysdeps/xos'
    sources = compiled_sources() + [Path(__file__).resolve(),
                                   ROOT / 'tests/fixtures/glibc_g3/terminal_host_aliases.h']
    sources += list(overlay.rglob('*.h'))
    sources += [path for name in ('src/shared/include/xos', 'src/user/include/xos')
                for path in (ROOT / name).rglob('*.hpp')]
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(set(sources))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    overlay = ROOT / 'src/ports/glibc/sysdeps/xos'
    flags = ['-D_GNU_SOURCE', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wconversion', '-Wshadow',
             '-I', str(overlay), '-I', str(ROOT / 'src/shared/include'),
             '-idirafter', str(ROOT / 'src/user/include')]
    environment = os.environ.copy()
    if args.sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        environment['ASAN_OPTIONS'] = 'detect_leaks=0:abort_on_error=1'
        environment['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
    report = {'status': 'failed', 'scope': 'real libc FD/termios/native client; kernel and files peer simulated',
              'sanitizers': ['address', 'undefined'] if args.sanitize else [],
              'leak_sanitizer': 'not_run', 'guest': 'not_run_by_this_runner', 'commands': [], 'results': [],
              'source_snapshot_verified': False}
    sources = compiled_sources()

    def run(command, name):
        report['commands'].append(command)
        result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=90)
        (output/(name+'.log')).write_text(result.stdout+result.stderr)
        if result.returncode:
            raise RuntimeError(name+' failed: '+str(result.returncode)+'\n'+result.stdout+result.stderr)
        return result.stdout

    try:
        report['sources'] = source_snapshot()
        objects = []
        for index, source in enumerate(sources):
            obj = output/(str(index)+'.o')
            extra = []
            if source.name in ('ioctl.c', 'select.c'):
                extra += ['-include', str(ROOT/'tests/fixtures/glibc_g3/terminal_host_aliases.h')]
            if source.name == 'select.c':
                extra.append('-DXOS_GLIBC_CLOCK_TEST')
            compiler = os.getenv('CC', 'gcc') if source.suffix=='.c' else os.getenv('CXX', 'g++')
            language = '-std=c11' if source.suffix=='.c' else '-std=c++20'
            run([compiler, language, '-DXOS_GLIBC_FILE_TEST', *flags, *extra, '-c', str(source), '-o', str(obj)], 'compile-'+str(index))
            objects.append(str(obj))
        binary=output/'terminal_test'
        run([os.getenv('CXX','g++'),*flags,*objects,'-pthread','-o',str(binary)],'link')
        for case in CASES:
            text=run([str(binary),case],case)
            assert text.strip() == 'PASS glibc_terminal '+case
            report['results'].append({'case':case,'status':'passed'})
            print(text,end='')
        current_sources = source_snapshot()
        if current_sources != report['sources']:
            report['sources_after'] = current_sources
            raise RuntimeError('source inputs changed during qualification')
        report['source_snapshot_verified'] = True
        report['status']='passed'
        print('PASS',len(CASES),'glibc terminal groups')
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    main()
