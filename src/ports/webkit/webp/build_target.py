#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build WebP's static codec and demux from the locked release for XOS."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

PORT = Path(__file__).resolve().parent
ROOT = PORT.parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from glibc_g1_probe import clean_build_environment, tool_identity
from xypm_format import sha_file
from xypm_sdk_profile import metadata_snapshot, verify_profile

BUILD_PROGRAMS = ('ANIM_UTILS', 'CWEBP', 'DWEBP', 'GIF2WEBP', 'IMG2WEBP', 'VWEBP',
                  'WEBPINFO', 'LIBWEBPMUX', 'WEBPMUX', 'EXTRAS')


def build(args):
    lock, lock_hash = metadata_snapshot(PORT / 'source_lock.json')
    archive = args.archive.read_bytes()
    if len(archive) != lock['archive_bytes'] or sha256(archive).hexdigest() != lock['sha256']:
        raise ValueError('WebP release archive differs from the source lock')
    profile, profile_hash = metadata_snapshot(args.sdk_profile)
    binding = verify_profile(profile, 'glibc', args.sdk_build)
    if not {'cxx_runtime', 'threads'} <= set(profile['features']):
        raise ValueError('WebP requires the WebKit glibc C/C++ thread profile')
    manifest, sdk_hash = metadata_snapshot(args.sdk_build / 'manifest.json',
                                           profile['sdk_binding']['sdk_manifest_sha256'])
    tools = {}
    for suffix in ('gcc', 'as', 'ld', 'ar', 'ranlib'):
        name = 'x86_64-elf-' + suffix
        tool = tool_identity(name)
        if not tool['available'] or tool['sha256'] != manifest['tools'][name]['sha256']:
            raise ValueError(f'{name} differs from the selected SDK toolchain')
        tools[suffix] = tool

    out = args.output
    if out.is_relative_to(args.sdk_build) or out.is_relative_to(ROOT / 'src'):
        raise ValueError('WebP output must be outside the source and SDK')
    out.mkdir(parents=True)
    source = out / lock['archive_root']
    prefix = out / 'prefix'
    work = out / 'cmake'
    with tarfile.open(fileobj=BytesIO(archive), mode='r:gz') as release:
        release.extractall(out, filter='data')
    for name, digest in lock['notices'].items():
        if sha_file(source / name) != digest or sha_file(PORT / (name + '.upstream')) != digest:
            raise ValueError(f'WebP upstream notice changed: {name}')

    binutils = out / 'binutils'
    binutils.mkdir()
    for name in ('as', 'ld'):
        (binutils / name).symlink_to(tools[name]['path'])
    wrapper = PORT.parent / 'icu/xos-compiler'
    cc = out / 'cc'
    cc.symlink_to(wrapper)
    sdk = args.sdk_build / 'sysroot'
    env, _ = clean_build_environment(os.environ)
    env.update(LC_ALL='C', COMPILER_PATH=str(binutils), XOS_ICU_SDK=str(sdk), XOS_ICU_CC=tools['gcc']['path'])

    def run(stage, command):
        with (out / (stage + '.log')).open('w') as log:
            subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)

    patch = PORT / 'xos_pthread_flags.patch'
    if sha_file(patch) != lock['patch_sha256']:
        raise ValueError('WebP target patch differs from the source lock')
    run('patch', ['patch', '--batch', '--fuzz=0', '-p1', '-d', source, '-i', patch])
    run('configure', ['cmake', '-S', source, '-B', work, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
                      '-DCMAKE_SYSTEM_NAME=XOS', '-DCMAKE_SYSTEM_PROCESSOR=x86_64',
                      '-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY', f'-DCMAKE_SYSROOT={sdk}',
                      f'-DCMAKE_C_COMPILER={cc}', f'-DCMAKE_AR={tools["ar"]["path"]}',
                      f'-DCMAKE_RANLIB={tools["ranlib"]["path"]}', f'-DCMAKE_INSTALL_PREFIX={prefix}',
                      '-DCMAKE_INSTALL_LIBDIR=lib', '-DBUILD_SHARED_LIBS=OFF',
                      *[f'-DWEBP_BUILD_{name}=OFF' for name in BUILD_PROGRAMS]])
    if '#define WEBP_USE_THREAD 1' not in (work / 'src/webp/config.h').read_text().splitlines():
        raise ValueError('WebP target configuration did not retain pthread support')
    run('build', ['cmake', '--build', work, '--parallel', str(args.jobs)])
    run('install', ['cmake', '--install', work])
    notices = prefix / 'share/licenses/libwebp'
    notices.mkdir(parents=True)
    for name in lock['notices']:
        shutil.copyfile(source / name, notices / name)
    libraries = ('libwebp.a', 'libwebpdemux.a', 'libsharpyuv.a')
    for library in libraries:
        members = subprocess.check_output([tools['ar']['path'], 't', prefix / 'lib' / library], env=env)
        if not members:
            raise ValueError(f'Empty target library: {library}')
    if sha_file(args.sdk_profile) != profile_hash or verify_profile(profile, 'glibc', args.sdk_build) != binding:
        raise ValueError('WebP SDK inputs changed during the build')
    receipt = {'status': 'static_webp_installed', 'source_lock_sha256': lock_hash,
               'archive_sha256': lock['sha256'], 'patch_sha256': lock['patch_sha256'], 'builder_sha256': sha_file(Path(__file__)),
               'compiler_wrapper_sha256': sha_file(wrapper), 'sdk_manifest_sha256': sdk_hash,
               'sdk_profile_sha256': profile_hash, 'target_tools': {name: tool['sha256'] for name, tool in tools.items()},
               'files': {path.relative_to(prefix).as_posix(): sha_file(path)
                         for path in sorted(prefix.rglob('*')) if path.is_file()}}
    (out / 'manifest.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'sdk-build', 'sdk-profile', 'output'):
        parser.add_argument('--' + name, type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument('--jobs', type=int, default=2)
    options = parser.parse_args()
    if options.jobs < 1:
        parser.error('--jobs must be positive')
    build(options)
