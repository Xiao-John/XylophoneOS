#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the LibXml2 prerequisite used by WebCore on the glibc SDK."""

import argparse
from hashlib import file_digest
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

port = Path(__file__).resolve().parent
root = port.parents[3]
sys.path.insert(0, str(root / 'scripts'))
from build_glibc_program import verify_elf
from glibc_g1_probe import clean_build_environment, tool_identity
from xypm_sdk_profile import metadata_snapshot, verify_profile


def digest(path):
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def build(args):
    lock_path = port / 'source_lock.json'
    lock = json.loads(lock_path.read_bytes())
    if args.archive.stat().st_size != lock['archive_bytes'] or digest(args.archive) != lock['sha256']:
        raise ValueError('LibXml2 archive differs from the source lock')
    webkit_lock = port.parent / 'source_lock.json'
    profile = json.loads(args.sdk_profile.read_bytes())
    binding = verify_profile(profile, 'glibc', args.sdk_build)
    expected_tree = json.loads(webkit_lock.read_bytes())['llint_icu']['sdk_tree_sha256']
    if 'cxx_runtime' not in profile['features'] or binding['sdk_tree_sha256'] != expected_tree:
        raise ValueError('LibXml2 must use the glibc C/C++ SDK selected for WebKit')
    sdk_manifest, sdk_hash = metadata_snapshot(args.sdk_build / 'manifest.json',
                                              profile['sdk_binding']['sdk_manifest_sha256'])
    tools = {}
    for suffix in ('gcc', 'as', 'ld', 'ar', 'ranlib'):
        name = 'x86_64-elf-' + suffix
        identity = tool_identity(name)
        if identity.get('sha256') != sdk_manifest['tools'][name]['sha256']:
            raise ValueError(f'{name} differs from the bound glibc toolchain')
        tools[suffix] = identity

    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    source = output / lock['archive_root']
    prefix, work, drivers = (output / name for name in ('prefix', 'cmake', 'drivers'))
    drivers.mkdir()
    driver = port.parent / 'icu/xos-compiler'
    cc = drivers / 'cc'
    cc.symlink_to(driver)
    binutils = drivers / 'binutils'
    binutils.mkdir()
    for name in ('as', 'ld'):
        (binutils / name).symlink_to(tools[name]['path'])
    sdk = args.sdk_build / 'sysroot'
    env, _ = clean_build_environment(os.environ)
    env.update(LC_ALL='C', COMPILER_PATH=str(binutils), XOS_ICU_SDK=str(sdk),
               XOS_ICU_CC=tools['gcc']['path'])

    def run(stage, command):
        log = output / (stage + '.log')
        with log.open('w') as stream:
            status = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT)
        if status.returncode:
            raise RuntimeError(f'{stage} failed; see {log}')

    run('unpack', ['tar', '-xJf', args.archive, '-C', output])
    notice = source / lock['license_member']
    if digest(notice) != lock['license_sha256'] or notice.read_bytes() != (port / 'LICENSE.upstream').read_bytes():
        raise ValueError('LibXml2 notice differs from the locked upstream release')
    run('configure', ['cmake', '-S', source, '-B', work, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
                      '-DCMAKE_SYSTEM_NAME=XOS', '-DCMAKE_SYSTEM_PROCESSOR=x86_64',
                      '-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY', f'-DCMAKE_SYSROOT={sdk}',
                      f'-DCMAKE_C_COMPILER={cc}', f'-DCMAKE_AR={tools["ar"]["path"]}',
                      f'-DCMAKE_RANLIB={tools["ranlib"]["path"]}', f'-DCMAKE_INSTALL_PREFIX={prefix}',
                      '-DCMAKE_INSTALL_LIBDIR=lib', '-DBUILD_SHARED_LIBS=OFF',
                      '-DLIBXML2_WITH_PROGRAMS=OFF', '-DLIBXML2_WITH_TESTS=OFF',
                      '-DLIBXML2_WITH_MODULES=OFF', '-DLIBXML2_WITH_ICONV=OFF', '-DLIBXML2_WITH_ZLIB=OFF'])
    run('build', ['cmake', '--build', work, '--parallel', str(args.jobs)])
    run('install', ['cmake', '--install', work])
    installed_notice = prefix / 'share/licenses/libxml2/LICENSE'
    installed_notice.parent.mkdir(parents=True)
    shutil.copyfile(notice, installed_notice)
    source_file = root / 'tests/fixtures/webkit/xml_push.c'
    executable = output / 'xml_push.elf'
    run('link', [cc, '-std=c17', '-O2', '-I', prefix / 'include/libxml2', source_file,
                 prefix / 'lib/libxml2.a', '-o', executable])
    verify_elf(executable)
    if digest(args.archive) != lock['sha256'] or verify_profile(profile, 'glibc', args.sdk_build) != binding:
        raise ValueError('build inputs changed during the target build')
    artifacts = [executable, *(path for path in sorted(prefix.rglob('*')) if path.is_file())]
    receipt = {'status': 'target_libxml2_linked', 'builder_sha256': digest(Path(__file__)),
               'libxml2_lock_sha256': digest(lock_path), 'webkit_lock_sha256': digest(webkit_lock),
               'archive_sha256': lock['sha256'], 'license_sha256': lock['license_sha256'],
               'sdk_manifest_sha256': sdk_hash, 'profile_binding': binding,
               'compiler_wrapper_sha256': digest(driver), 'fixture_sha256': digest(source_file),
               'target_tools': {name: item['sha256'] for name, item in tools.items()},
               'artifacts': {str(path.relative_to(output)): digest(path) for path in artifacts}}
    (output / 'manifest.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'sdk-build', 'sdk-profile', 'output'):
        parser.add_argument('--' + name, type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument('--jobs', type=int, default=2)
    arguments = parser.parse_args()
    if arguments.jobs < 1:
        parser.error('--jobs must be positive')
    build(arguments)
