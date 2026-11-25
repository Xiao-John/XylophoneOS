#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise wait acceptance identity gates with coherent synthetic systems."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
import process_wait_any_guest as guest_runner
from kernel_process_wait_race_test import definition


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    paths = [Path(__file__).resolve(), ROOT / 'tests/process_wait_any_guest.py',
             ROOT / 'tests/shell_launch_support.py', ROOT / 'tests/kernel_process_wait_race_test.py',
             ROOT / 'tests/fixtures/process_wait/probe.cpp', ROOT / 'src/kernel/arch/x86_64/tasks.cpp',
             ROOT / 'src/shared/include/xos/process_abi.hpp', ROOT / 'src/shared/include/xos/abi_types.hpp']
    inputs = {str(path.relative_to(ROOT)): sha(path) for path in paths}
    report = {'status': 'failed', 'sources': inputs, 'guest': 'not_run', 'results': [],
              'scope': 'synthetic identity gates, extracted sentinel predicate and actual host wait harness'}

    def passed(name):
        report['results'].append(name)
        print('PASS ' + name)

    def write_system(directory, *, build_id='1111111111111111', iso=b'synthetic ISO A', sdk_extra=None):
        directory.mkdir(exist_ok=True)
        sdk = directory / 'sdk'
        (sdk / 'lib').mkdir(parents=True, exist_ok=True)
        for name in ('crt0_posix.o', 'user.ld', 'lib/libxos.a', 'lib/libxos_loader.a', 'lib/libc.a', 'lib/libm.a'):
            (sdk / name).write_bytes(b'synthetic hash-bound artifact')
        (sdk / 'manifest.json').write_text(json.dumps({'build_id': build_id, 'extra': sdk_extra}))
        (directory / 'xos-install.iso').write_bytes(iso)
        artifact_paths = [directory / 'xos-install.iso'] + sorted(p for p in sdk.rglob('*') if p.is_file())
        manifest = {'build_id': build_id, 'source_sha256': 'synthetic source selection',
                    'sources': {'tests/fixtures/process_wait/probe.cpp': inputs['tests/fixtures/process_wait/probe.cpp']},
                    'artifacts': {str(path.relative_to(directory)): {'sha256': sha(path)} for path in artifact_paths}}
        (directory / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True) + '\n')

    def rejection(name, change):
        directory = output / name
        write_system(directory)
        initial = guest_runner.system_identity(directory)
        change(directory)
        guest_runner.bind_system(directory)  # The replacement is internally coherent.
        try:
            guest_runner.verify_system_identity(directory, initial)
        except RuntimeError as error:
            if 'system identity changed during acceptance' not in str(error):
                raise
            passed(name)
        else:
            raise AssertionError('coherent replacement was accepted: ' + name)

    try:
        stable = output / 'stable'
        write_system(stable)
        guest_runner.verify_system_identity(stable, guest_runner.system_identity(stable))
        passed('unchanged_system')
        rejection('coherent_build_replacement', lambda p: write_system(p, build_id='2222222222222222'))
        rejection('coherent_iso_replacement', lambda p: write_system(p, iso=b'synthetic ISO B'))
        rejection('coherent_sdk_replacement', lambda p: write_system(p, sdk_extra='replacement'))
        rejection('manifest_bytes_replacement', lambda p: (p / 'manifest.json').write_bytes(
            (p / 'manifest.json').read_bytes() + b'\n'))

        # A change between the initial manifest snapshot and bind_system is
        # also rejected, before the identity can be recorded as a baseline.
        binding = output / 'binding_change'
        write_system(binding)
        original = guest_runner.bind_system

        def substituted(directory):
            write_system(directory, build_id='3333333333333333')
            return original(directory)

        guest_runner.bind_system = substituted
        try:
            try:
                guest_runner.system_identity(binding)
            except RuntimeError as error:
                if 'changed while binding' not in str(error):
                    raise
                passed('manifest_change_during_binding')
            else:
                raise AssertionError('binding-time replacement accepted')
        finally:
            guest_runner.bind_system = original

        fixture = (ROOT / 'tests/fixtures/process_wait/probe.cpp').read_text()
        predicate = definition(fixture, 'process_status sentinel()') + definition(fixture, 'bool unchanged(')
        mutations = ['version = 0', 'outcome = process_outcome::exited', 'pid = 0',
                     'code = 0', 'vector = 0', 'address = 0', 'instruction = 0']
        source = output / 'status_fields.cpp'
        source.write_text('#include <xos/process_abi.hpp>\nusing namespace xos;\n' + predicate
                          + 'int main() { if (!unchanged(sentinel())) return 1;\n'
                          + '\n'.join('{ auto value = sentinel(); value.' + mutation
                                      + '; if (unchanged(value)) return ' + str(index + 2) + '; }'
                                      for index, mutation in enumerate(mutations)) + '\nreturn 0; }\n')
        compiler = shutil.which(os.environ.get('CXX', 'c++'))
        if compiler is None:
            raise RuntimeError('host C++ compiler is missing')
        binary = output / 'status_fields'
        subprocess.run([compiler, '-std=c++20', '-Wall', '-Wextra', '-Werror',
                        '-I', str(ROOT / 'src/shared/include'), str(source), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
        passed('all_seven_status_fields_and_unchanged_control')

        # Mutate a private source copy only after extraction, when the compiler
        # starts. The real host harness must report the bytes it compiled.
        source_copy = output / 'tasks.cpp'
        source_copy.write_bytes((ROOT / 'src/kernel/arch/x86_64/tasks.cpp').read_bytes())
        original_sha = sha(source_copy)
        wrapper = output / 'mutating_cxx'
        wrapper.write_text('#!' + sys.executable + '\nimport os,sys\nfrom pathlib import Path\n'
                           + 'p=Path(' + repr(str(source_copy)) + ')\n'
                           + 'p.write_bytes(p.read_bytes()+b"\\n// private post-extraction mutation\\n")\n'
                           + 'os.execv(' + repr(compiler) + ',[' + repr(compiler) + ',*sys.argv[1:]])\n')
        wrapper.chmod(0o755)
        harness = output / 'snapshot_harness'
        with (output / 'snapshot_harness.log').open('w') as log:
            subprocess.run([sys.executable, str(ROOT / 'tests/kernel_process_wait_race_test.py'),
                            '--source', str(source_copy), '--output', str(harness)],
                           env={**os.environ, 'CXX': str(wrapper)}, check=True, stdout=log)
        receipt = json.loads((harness / 'report.json').read_text())
        if receipt['status'] != 'pass' or receipt['source_sha256'] != original_sha or sha(source_copy) == original_sha:
            raise AssertionError('extraction receipt did not retain the source snapshot')
        passed('extracted_source_digest_survives_later_file_change')
        if inputs != {str(path.relative_to(ROOT)): sha(path) for path in paths}:
            raise RuntimeError('acceptance host inputs changed during verification')
        report['status'] = 'passed'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
