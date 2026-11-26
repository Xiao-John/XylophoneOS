#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run real host qualification while changing one input immediately after link."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
    'files_extra': ('tests/glibc_files_extra_host.py', 'files_extra',
                    'src/ports/glibc/sysdeps/xos/xos_file_positioned.c'),
    'terminal': ('tests/glibc_terminal_host.py', 'terminal_test',
                 'tests/fixtures/glibc_g3/terminal_runtime.cpp'),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=PROFILES, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', help='Use this Git revision of the runner to reproduce the old false pass')
    parser.add_argument('--expect', choices=('passed', 'failed'), default='failed')
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    checkout = output / 'checkout'
    runner, binary_name, mutation = PROFILES[args.profile]
    report = {'status': 'failed', 'profile': args.profile, 'expected_runner_status': args.expect,
              'injection': 'append a valid comment to a source only after the real final link succeeds'}
    try:
        # A disposable input copy keeps the real checkout and concurrent builds untouched.
        directories = ['src/ports/glibc/sysdeps/xos', 'src/shared/include', 'src/user/include',
                       'src/third_party/fatfs', 'tests/fixtures/file_semantics', 'tests/fixtures/glibc_g3']
        files = [runner, 'scripts/make_work_disk.py', 'src/user/services/files.cpp',
                 'src/user/services/fatfs_unicode.cpp', 'src/user/loader/elf.cpp', 'src/user/sdk/file_client.cpp',
                 'src/user/sdk/terminal_client.cpp', 'src/user/sdk/text.cpp',
                 'src/ports/glibc/terminal_support.cpp']
        for name in directories:
            shutil.copytree(ROOT / name, checkout / name)
        for name in files:
            destination = checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)
        if args.baseline:
            original = subprocess.check_output(['git', 'show', args.baseline + ':' + runner], cwd=ROOT)
            (checkout / runner).write_bytes(original)
        report['runner_sha256'] = digest(checkout / runner)
        target = checkout / mutation
        report['mutation_path'] = mutation
        report['input_sha256'] = digest(target)
        wrapper = output / 'cxx'
        wrapper.write_text("""#!/usr/bin/env python3
import hashlib, json, os
from pathlib import Path
import subprocess, sys
result = subprocess.run([os.environ['XOS_BINDING_REAL_CXX'], *sys.argv[1:]])
if result.returncode == 0 and '-o' in sys.argv:
    result_path = Path(sys.argv[sys.argv.index('-o') + 1])
    if result_path.name == os.environ['XOS_BINDING_BINARY']:
        source = Path(os.environ['XOS_BINDING_MUTATION'])
        source.write_bytes(source.read_bytes() + b'\\n/* qualification input changed after final link */\\n')
        Path(os.environ['XOS_BINDING_MARKER']).write_text(json.dumps({'binary_sha256': hashlib.sha256(result_path.read_bytes()).hexdigest()}))
sys.exit(result.returncode)
""")
        wrapper.chmod(0o755)
        real_cxx = shutil.which(os.environ.get('CXX', 'g++'))
        if not real_cxx:
            raise RuntimeError('host C++ compiler unavailable')
        environment = {**os.environ, 'CXX': str(wrapper), 'XOS_BINDING_REAL_CXX': real_cxx,
                       'XOS_BINDING_BINARY': binary_name, 'XOS_BINDING_MUTATION': str(target),
                       'XOS_BINDING_MARKER': str(output / 'mutation.json')}
        command = [sys.executable, str(checkout / runner), '--output', str(output / 'qualification')]
        result = subprocess.run(command, cwd=checkout, env=environment, text=True,
                                capture_output=True, timeout=240)
        (output / 'runner.log').write_text(result.stdout + result.stderr)
        report.update(command=command, returncode=result.returncode, changed_sha256=digest(target))
        marker = json.loads((output / 'mutation.json').read_text())
        report['linked_binary_sha256'] = marker['binary_sha256']
        qualification = json.loads((output / 'qualification/report.json').read_text())
        report['runner_status'] = qualification['status']
        report['recorded_source_sha256'] = qualification.get('sources', {}).get(mutation)
        report['runner_error'] = qualification.get('error')
        if report['input_sha256'] == report['changed_sha256']:
            raise RuntimeError('source mutation did not happen')
        if qualification['status'] != args.expect or (result.returncode == 0) != (args.expect == 'passed'):
            raise RuntimeError('unexpected runner result after real post-link source mutation')
        if args.expect == 'failed':
            if 'source inputs changed during qualification' not in qualification.get('error', ''):
                raise RuntimeError('failure must come from source verification, not compilation or runtime')
            if report['recorded_source_sha256'] != report['input_sha256']:
                raise RuntimeError('failed qualification lost the original pre-build digest')
        elif report['recorded_source_sha256'] != report['changed_sha256']:
            raise RuntimeError('baseline did not reproduce the post-build digest false binding')
        report['status'] = 'passed'
        print('PASS', args.profile, 'real post-link mutation ->', args.expect)
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
