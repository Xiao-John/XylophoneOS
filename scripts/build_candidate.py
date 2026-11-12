#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Serial current-source candidate build with explicit unrun guest qualification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from bootstrap_toolchain import toolchain_environment

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new directory below build/candidates/')
    parser.add_argument('--toolchain-prefix', type=Path)
    parser.add_argument('--newlib-archive', type=Path)
    parser.add_argument('--gcc-source', type=Path)
    parser.add_argument('--guest', action='store_true', help='run the existing make smoke gate')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT / 'build/candidates'):
        parser.error('--output must be a new directory below build/candidates/')
    if bool(args.newlib_archive) != bool(args.gcc_source):
        parser.error('supply --newlib-archive and --gcc-source together for the threaded C++ SDK')
    output.mkdir(parents=True)
    report = {'status': 'building', 'source_commit': git(['rev-parse', 'HEAD']),
              'working_diff_sha256': hashlib.sha256(subprocess.check_output(['git', 'diff', 'HEAD'], cwd=ROOT)).hexdigest(),
              'guest_qualification': 'pending' if args.guest else 'not_run',
              'steps': [], 'artifacts': {}, 'published': False}
    env = os.environ.copy()
    if args.toolchain_prefix:
        env.update(toolchain_environment(args.toolchain_prefix.resolve()))
    commands = [('system', [sys.executable, 'scripts/build.py']),
                ('dash', [sys.executable, 'scripts/build_dash.py', '--receipt', str(output / 'dash_manifest.json')]),
                ('install_iso', [sys.executable, 'scripts/build_install_iso.py', '--dash-manifest', str(output / 'dash_manifest.json')]),
                ('licenses', [sys.executable, 'scripts/license_audit.py'])]
    if args.newlib_archive:
        work = output / 'threaded_newlib'
        commands.extend([
            ('threaded_newlib', [sys.executable, 'scripts/build_threading_newlib.py', '--archive',
                                str(args.newlib_archive.resolve()), '--output', str(work)]),
            ('threaded_sdk', [sys.executable, 'scripts/build_threading_sdk.py', '--newlib-prefix',
                             str(work / 'prefix'), '--gcc-source', str(args.gcc_source.resolve()),
                             '--output', str(output / 'threading_sdk'), '--cpp-work-dir',
                             str(output / 'threading_cpp'), '--logs-dir', str(output / 'threading_sdk_logs'), '--cpp']),
        ])
    if args.guest:
        commands.append(('smoke', ['make', 'smoke']))
    try:
        for name, command in commands:
            step = {'name': name, 'argv': command, 'log': name + '.log', 'status': 'running'}
            report['steps'].append(step)
            save(output, report)
            with (output / step['log']).open('w') as log:
                result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            step['returncode'] = result.returncode
            step['status'] = 'passed' if result.returncode == 0 else 'failed'
            if result.returncode:
                raise RuntimeError(name + ' failed; see ' + str(output / step['log']))
        system = json.loads((ROOT / 'build/manifest.json').read_text())
        install = json.loads((ROOT / 'build/install_manifest.json').read_text())
        if install['build_id'] != system['build_id'] or install['kernel_sha256'] != system['artifacts']['kernel.bin']['sha256']:
            raise ValueError('install ISO does not belong to the final system build')
        report['build_id'] = system['build_id']
        frozen = output / 'system'
        frozen.mkdir()
        for relative, item in system['artifacts'].items():
            source = ROOT / 'build' / relative
            if sha(source) != item['sha256']:
                raise ValueError('artifact changed after build: ' + relative)
            target = frozen / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            report['artifacts']['system/' + relative] = item['sha256']
        for name in ('manifest.json', 'install_manifest.json', 'license_report.json', 'xos-install-dash.iso'):
            source = ROOT / 'build' / name
            shutil.copyfile(source, frozen / name)
            report['artifacts']['system/' + name] = sha(source)
        if args.newlib_archive:
            report['threaded_sdk_manifest_sha256'] = sha(output / 'threading_sdk/manifest.json')
        report['status'] = 'built_smoke_passed' if args.guest else 'built_unverified'
        report['guest_qualification'] = 'smoke_passed' if args.guest else 'not_run'
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        raise
    finally:
        save(output, report)
    print(output / 'candidate_manifest.json')


def git(arguments):
    return subprocess.check_output(['git', *arguments], cwd=ROOT, text=True).strip()


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def save(output, report):
    (output / 'candidate_manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit('candidate build: ' + str(error))
