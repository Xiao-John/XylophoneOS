#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build ICU4C host data tools and static XOS target libraries in separate directories."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from prepare_target import sha256

PORT = Path(__file__).resolve().parent
sys.path.insert(0, str(PORT.parents[3] / 'scripts'))
from glibc_g1_probe import clean_build_environment, select_gnu_make, tool_identity
from xypm_sdk_profile import verify_profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('archive', 'signature', 'keys', 'sdk-build', 'sdk-profile', 'output'):
        parser.add_argument('--' + option, type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')

    sdk_build = args.sdk_build.resolve(strict=True)
    sdk_manifest = json.loads((sdk_build / 'manifest.json').read_text())
    profile = json.loads(args.sdk_profile.read_text())
    binding = verify_profile(profile, 'glibc', sdk_build)
    if 'cxx_runtime' not in profile['features']:
        parser.error('the XOS SDK candidate must include the C++ runtime')
    include_dirs = profile['sdk_binding']['cxx_runtime']['include_directories']
    tools = {}
    for name in ('gcc', 'g++', 'ar', 'ranlib', 'ld', 'as'):
        name = 'x86_64-elf-' + name
        actual = tool_identity(name)
        if actual.get('sha256') != sdk_manifest['tools'][name]['sha256']:
            parser.error(name + ' differs from the XOS SDK build')
        tools[name] = actual

    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    env, _ = clean_build_environment(os.environ)
    env = {name: value for name, value in env.items()
           if name != 'LIBS' and not name.startswith(('ac_cv_', 'icu_cv_'))}
    env['LC_ALL'] = 'C'
    env['CONFIG_SITE'] = os.devnull
    env['CFLAGS'] = env['CXXFLAGS'] = '-O1 -g0'
    make = select_gnu_make()['path']
    args_for_static = ['--disable-shared', '--enable-static', '--disable-samples', '--disable-tests',
                       '--disable-extras']

    def run(name, command, directory, environment):
        report = output / (name + '.log')
        with report.open('w') as log:
            result = subprocess.run(command, cwd=directory, env=environment, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise SystemExit(f'{name} failed, see {report}')

    run('prepare', [sys.executable, str(PORT / 'prepare_target.py'), '--archive', str(args.archive.resolve()),
                    '--signature', str(args.signature.resolve()), '--keys', str(args.keys.resolve()),
                    '--output', str(output / 'src')], output, env)
    source = output / 'src/icu/source'
    configure = str(source / 'configure')
    host = output / 'host'
    host.mkdir()
    run('host-configure', [configure, '--with-data-packaging=archive', *args_for_static], host, env)
    run('host-build', [make, '-j', str(args.jobs)], host, env)

    target = output / 'target'
    target.mkdir()
    drivers = output / 'drivers'
    drivers.mkdir()
    for driver in ('cc', 'cxx'):
        (drivers / driver).symlink_to(PORT / 'xos-compiler')
    header_list = drivers / 'cxx-includes.txt'
    header_list.write_text('\n'.join(include_dirs) + '\n')
    target_env = env | {'CC': str(drivers / 'cc'), 'CXX': str(drivers / 'cxx'),
                        'AR': tools['x86_64-elf-ar']['path'], 'RANLIB': tools['x86_64-elf-ranlib']['path'],
                        'XOS_ICU_CC': tools['x86_64-elf-gcc']['path'], 'XOS_ICU_CXX': tools['x86_64-elf-g++']['path'],
                        'XOS_ICU_SDK': str(sdk_build / 'sysroot'), 'XOS_ICU_CXX_INCLUDES': str(header_list),
                        'ac_cv_func_mmap_ok': 'no'}
    host_triple = subprocess.check_output(['sh', source / 'config.guess'], env=env, text=True).strip()
    prefix = output / 'install'
    run('target-configure', [configure, f'--build={host_triple}', '--host=x86_64-unknown-xos',
                            f'--with-cross-build={host}', f'--prefix={prefix}', '--disable-dyload',
                            '--disable-tools', *args_for_static], target, target_env)
    run('target-build', [make, '-j', str(args.jobs)], target, target_env)
    run('target-install', [make, 'install'], target, target_env)
    if verify_profile(json.loads(args.sdk_profile.read_text()), 'glibc', sdk_build) != binding:
        raise SystemExit('XOS SDK binding changed during the ICU build')
    artifacts = {f'lib/libicu{name}.a': sha256(prefix / f'lib/libicu{name}.a') for name in ('data', 'i18n', 'uc')}
    lock = json.loads((PORT / 'source_lock.json').read_text())
    report = {'status': 'static_icu_built', 'sdk_tree_sha256': binding['sdk_tree_sha256'],
              'sources': {field: lock[field] for field in ('archive_sha256', 'signature_sha256', 'keys_sha256')},
              'recipe': {name: sha256(PORT / name) for name in ('build_target.py', 'prepare_target.py',
                                                               'source_lock.json', 'xos-compiler')},
              'tools': {name: info['sha256'] for name, info in tools.items()}, 'artifacts': artifacts}
    (output / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
