#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real closure/verifiers with modeled immutable Files OFDs, plus actual target ELFs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from toolchain import audit, tool

CASES = ('policy_validation', 'wrong_sdk', 'configure_close_unknown', 'configure_open_unknown', 'acquire_pins',
         'activation_rollback', 'failed_activation', 'digest_failure', 'sdk_failure',
         'release_unknown', 'read_unknown', 'absolute_deadline', 'restore_and_heap', 'revoke_active',
         'elf_needed', 'elf_soname', 'elf_wx', 'elf_relro', 'elf_relocation', 'elf_tls', 'elf_version',
         'bootstrap_thread_arena', 'bootstrap_capsule')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    paths = [ROOT / name for name in ('src/user/loader/dynamic/closure.cpp', 'src/user/loader/dynamic/authority.cpp',
             'src/user/loader/dynamic/generation.cpp',
             'src/user/loader/dynamic/identity.cpp', 'src/user/loader/dynamic/elf.cpp', 'src/user/loader/elf.cpp',
             'tests/fixtures/dynamic_closure_host.cpp')]
    tracked = [*paths, ROOT / 'tests/fixtures/dynamic_closure_object.cpp',
               ROOT / 'src/user/loader/dynamic/startup.hpp',
               ROOT / 'tests/fixtures/dynamic_closure_bootstrap.ld',
               ROOT / 'tests/fixtures/dynamic_closure_versions.map', Path(__file__)]
    tracked += [p for folder in ('src/user/include/xos', 'src/shared/include/xos')
                for p in (ROOT / folder).glob('*') if p.suffix in ('.h', '.hpp')]
    hashes = lambda: {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
    report = {'status': 'failed', 'scope': 'production closure/verifiers; modeled Files OFDs',
              'guest': 'not_run', 'sources': hashes(), 'toolchain': audit(), 'commands': [], 'results': []}
    include = ['-I', str(ROOT / 'src/shared/include'), '-I', str(ROOT / 'src/user/include')]
    def run(command, log):
        report['commands'].append(command)
        with (out / log).open('w') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
    try:
        for role, name in ((1, 'bootstrap.elf'), (2, 'interpreter.so'), (4, 'library.so'), (3, 'main.elf')):
            command = [tool('g++'), '-std=c++20', '-Os', '-ffreestanding', '-fno-exceptions', '-fno-rtti',
                       '-fno-stack-protector', '-fno-asynchronous-unwind-tables', '-fno-unwind-tables',
                       '-mno-red-zone', '-nostdinc++', '-DFIXTURE_ROLE=' + str(role), *include,
                       str(ROOT / 'tests/fixtures/dynamic_closure_object.cpp'), '-c',
                       '-fno-pic' if role == 1 else '-fPIC', '-o', str(out / (name + '.o'))]
            run(command, name + '_compile.log')
            command = [tool('ld'), '--hash-style=both', '--build-id=none', '-z', 'noexecstack',
                       '-z', 'relro', '-z', 'now', '-z', 'max-page-size=4096', str(out / (name + '.o')),
                       '-o', str(out / name)]
            if role == 1:
                command += ['-static', '-T', str(ROOT / 'tests/fixtures/dynamic_closure_bootstrap.ld')]
            elif role == 3:
                command += ['-pie', '-e', '_start', '--dynamic-linker', '/usr/lib/xos/glibc_dynamic_v1/ld_xos_x86_64.so.1',
                            str(out / 'library.so')]
            else:
                command += ['-shared', '-soname', 'ld_xos_x86_64.so.1' if role == 2 else 'libstdc++.so.6']
                if role == 2:
                    command += ['-e', '_start']
                else:
                    command += ['--version-script', str(ROOT / 'tests/fixtures/dynamic_closure_versions.map')]
            run(command, name + '_link.log')
        report['fixtures'] = {name: hashlib.sha256((out / name).read_bytes()).hexdigest()
                              for name in ('bootstrap.elf', 'interpreter.so', 'library.so', 'main.elf')}
        for kind in ('ordinary', 'sanitized'):
            binary = out / kind
            command = [os.environ.get('CXX', 'g++'), '-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                       '-Wconversion', '-Wshadow', *include, *map(str, paths), '-o', str(binary)]
            if kind == 'sanitized':
                command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
            run(command, kind + '_compile.log')
            for case in CASES:
                environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:abort_on_error=1', UBSAN_OPTIONS='halt_on_error=1')
                result = subprocess.run([str(binary), case, str(out)], capture_output=True, text=True, env=environment, timeout=20)
                (out / (kind + '_' + case + '.log')).write_text(result.stdout + result.stderr)
                report['results'].append({'kind': kind, 'case': case, 'returncode': result.returncode})
                if result.returncode or 'PASS dynamic-closure host ' + case not in result.stdout:
                    raise RuntimeError(kind + ' ' + case + ' failed')
                print(result.stdout.strip())
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
