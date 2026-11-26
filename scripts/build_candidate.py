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
from xypm_format import require
from xypm_sdk_profile import metadata_snapshot, relative_file, sdk_snapshot, verify_profile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new directory below build/candidates/')
    parser.add_argument('--toolchain-prefix', type=Path)
    parser.add_argument('--glibc-app-kit', type=Path,
                        help='use an independently staged glibc C/C++ application SDK for the installer shell')
    parser.add_argument('--newlib-archive', type=Path)
    parser.add_argument('--gcc-source', type=Path)
    parser.add_argument('--guest', action='store_true', help='run the existing make smoke gate')
    parser.add_argument('--installer-guest', action='store_true',
                        help='boot the selected glibc installer and verify dash on a fresh disk')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT / 'build/candidates'):
        parser.error('--output must be a new directory below build/candidates/')
    if bool(args.newlib_archive) != bool(args.gcc_source):
        parser.error('supply --newlib-archive and --gcc-source together for the threaded C++ SDK')
    if args.installer_guest and not args.glibc_app_kit:
        parser.error('--installer-guest requires --glibc-app-kit')
    app_sdk = inspect_app_kit(args.glibc_app_kit) if args.glibc_app_kit else None
    test_installer = app_sdk is not None and (args.installer_guest or args.guest)
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=ROOT)
    if untracked:
        parser.error('untracked files may be build inputs; commit or move them before candidate build')
    output.mkdir(parents=True)
    report = {'status': 'building', 'source_commit': git(['rev-parse', 'HEAD']),
              'working_diff_sha256': hashlib.sha256(subprocess.check_output(['git', 'diff', 'HEAD'], cwd=ROOT)).hexdigest(),
              'guest_qualification': 'pending' if args.guest else 'not_run',
              'steps': [], 'artifacts': {}, 'published': False}
    env = os.environ.copy()
    if args.toolchain_prefix:
        env.update(toolchain_environment(args.toolchain_prefix.resolve()))
    system_command = [sys.executable, 'scripts/build.py']
    dash_command = [sys.executable, 'scripts/build_dash.py', '--receipt', str(output / 'dash_manifest.json')]
    if app_sdk is not None:
        report['application_sdk'] = app_sdk
        report['installer_guest_qualification'] = 'not_run'
        kit = args.glibc_app_kit.absolute()
        system_command.append('--quiet-demos-on-launch')
        dash_command.extend(['--sdk', str(kit / 'sdk/sysroot'), '--glibc-profile', str(kit / 'profile.json')])
    commands = [('system', system_command),
                ('dash', dash_command),
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
        smoke_command = ['make', '-o', 'build', 'smoke'] if app_sdk is not None else ['make', 'smoke']
        commands.append(('smoke', smoke_command))
    if test_installer:
        commands.append(('installer_smoke', [sys.executable, 'tests/iso_dash_install.py',
                         '--external', '--report', str(output / 'installer_guest_report.json')]))
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
                if name == 'installer_smoke':
                    report['installer_guest_qualification'] = 'failed'
                raise RuntimeError(name + ' failed; see ' + str(output / step['log']))
        system = json.loads((ROOT / 'build/manifest.json').read_text())
        install = json.loads((ROOT / 'build/install_manifest.json').read_text())
        if install['build_id'] != system['build_id'] or install['kernel_sha256'] != system['artifacts']['kernel.bin']['sha256']:
            raise ValueError('install ISO does not belong to the final system build')
        if app_sdk is not None:
            require(inspect_app_kit(args.glibc_app_kit) == app_sdk,
                    'application kit changed while building the candidate')
            dash, dash_receipt_hash = metadata_snapshot(output / 'dash_manifest.json')
            require(system['quiet_demos_on_launch'] is True and dash['profile'] == 'dash_glibc_preview'
                    and dash['inputs']['profile'] == app_sdk['profile_sha256']
                    and dash['inputs']['sdk/manifest.json'] == app_sdk['sdk_manifest_sha256']
                    and dash['sha256'] == install['dash_sha256'],
                    'installer dash differs from the selected application SDK')
            report['artifacts']['dash_manifest.json'] = dash_receipt_hash
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
            if sha(target) != item['sha256']:
                raise ValueError('frozen artifact differs from manifest: ' + relative)
            report['artifacts']['system/' + relative] = item['sha256']
        for name in ('manifest.json', 'install_manifest.json', 'license_report.json', 'xos-install-dash.iso'):
            source = ROOT / 'build' / name
            expected = sha(source)
            shutil.copyfile(source, frozen / name)
            if sha(frozen / name) != expected:
                raise ValueError('frozen artifact changed: ' + name)
            report['artifacts']['system/' + name] = expected
        if args.newlib_archive:
            report['threaded_sdk_manifest_sha256'] = sha(output / 'threading_sdk/manifest.json')
        if test_installer:
            guest_path = output / 'installer_guest_report.json'
            guest, guest_hash = metadata_snapshot(guest_path)
            require(guest['status'] == 'passed' and guest['build_id'] == system['build_id']
                    and guest['iso_sha256'] == report['artifacts']['system/xos-install-dash.iso'],
                    'install guest report does not bind the frozen candidate ISO')
            report['artifacts']['installer_guest_report.json'] = guest_hash
            report['installer_guest_qualification'] = 'passed'
        report['status'] = 'built_smoke_passed' if args.guest else 'built_unverified'
        report['guest_qualification'] = 'smoke_passed' if args.guest else 'not_run'
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        raise
    finally:
        save(output, report)
    print(output / 'candidate_manifest.json')


def inspect_app_kit(kit):
    require(kit.is_dir() and not kit.is_symlink(), 'application kit must be a real directory')
    profile, profile_file_hash = metadata_snapshot(relative_file(kit, 'profile.json'))
    require('cxx_runtime' in profile['features'], 'glibc application kit requires both C and C++')
    binding = verify_profile(profile, 'glibc', kit / 'sdk')
    kit_hash, _ = sdk_snapshot(kit)
    return {'profile_id': binding['profile_id'], 'profile_sha256': binding['profile_sha256'],
            'profile_file_sha256': profile_file_hash, 'sdk_tree_sha256': binding['sdk_tree_sha256'],
            'sdk_manifest_sha256': profile['sdk_binding']['sdk_manifest_sha256'], 'kit_tree_sha256': kit_hash}


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
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit('candidate build: ' + str(error))
