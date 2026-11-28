#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compose a glibc host SDK using the pinned Preview 2 host tools unchanged.

Run inside Preview 2. Packaging is not guest qualification; the separate host
recipe extracts the completed archive and runs its installed consumer smoke.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from package_glibc_sdk import APP_TOOLS
from verify_gcc_shared_source import verify_source as verify_gcc
from verify_glibc_source import verify_source as verify_glibc
from work_disk import host_tool
from xos_app import tree_receipt
from xypm_format import load_json, require, sha_file
from xypm_sdk_profile import verify_profile

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'config/sdk/glibc_host_preview.json'
SOURCE_PATHS = ('Makefile', 'VERSION', 'LICENSE', 'NOTICE', 'src', 'scripts', 'tests',
                'config', 'licenses', 'docs/reports/glibc_stock_fork_sdk_20261126/build_glibc_cxx.sh',
                'docs/reports/glibc_stock_fork_sdk_20261126/build_unwinder.sh',
                'docs/reports/glibc_stock_apps_20261126/external.c',
                'docs/reports/glibc_stock_apps_20261126/external.cpp',
                'docs/releases/glibc_host_sdk.md', '.github/workflows/glibc_sdk_prerelease.yml')


def write_json(path, data):
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + '\n')


def tree(root, *, exclude=()):
    result = {}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        if any(relative == value or relative.startswith(value + '/') for value in exclude):
            continue
        if path.is_symlink():
            result[relative] = {'symlink': os.readlink(path)}
        elif path.is_file():
            result[relative] = {'sha256': sha_file(path), 'mode': path.stat().st_mode & 0o777}
    return result


def receipt(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def source_snapshot(destination):
    destination.mkdir(parents=True, exist_ok=False)
    if (ROOT / '.git').exists():
        require(not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT),
                'commit tracked changes before capturing release sources')
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        # The license gate requires these registered evidence files and each
        # report directory's flat manifest as part of its build inputs.
        evidence = {item['evidence'].rstrip('/') for item in
                    load_json(ROOT / 'licenses/open_items.json')['items']}
        paths = sorted(set(SOURCE_PATHS) | evidence)
        for name in paths:
            require(not Path(name).is_absolute() and '..' not in Path(name).parts,
                    'source snapshot entry must be repository-relative')
        # git archive reads committed object bytes. Untracked files cannot
        # silently enter either the CI build tree or the source distribution.
        with subprocess.Popen(['git', 'archive', '--format=tar', commit, '--', *paths],
                              cwd=ROOT, stdout=subprocess.PIPE) as process:
            subprocess.run(['tar', '-xf', '-', '-C', str(destination)], stdin=process.stdout, check=True)
            process.stdout.close()
            require(process.wait() == 0, 'cannot capture committed source tree')
        binding = {'schema': 1, 'source_commit': commit, 'files': tree(destination)}
    else:
        # The isolated CI tree intentionally has no Git directory. Its binding
        # was produced from git archive by the outer host recipe above.
        binding = load_json(ROOT / 'host-sdk-source.json')
        require(binding['schema'] == 1 and re.fullmatch(r'[0-9a-f]{40}', binding['source_commit']),
                'invalid committed-source snapshot binding')
        for name, expected in binding['files'].items():
            require(not Path(name).is_absolute() and '..' not in Path(name).parts and
                    'sha256' in expected, 'source binding must contain regular relative files')
            source, target = ROOT / name, destination / name
            require(not source.is_symlink() and sha_file(source) == expected['sha256'] and
                    (source.stat().st_mode & 0o777) == expected['mode'], 'source snapshot changed: ' + name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        require(tree(destination) == binding['files'], 'copied source snapshot differs')
    write_json(destination / 'host-sdk-source.json', binding)
    return binding


def archive(directory, output):
    require(not output.exists(), 'archive already exists: ' + output.name)
    subprocess.run(['tar', '--sort=name', '--mtime=@0', '--owner=0', '--group=0', '--numeric-owner',
                    '--use-compress-program=zstd -T2 -8', '-cf', str(output),
                    '-C', str(directory.parent), directory.name], check=True)


def package(args):
    require(re.fullmatch(r'xos-sdk-glibc-preview-[0-9]+', args.tag), 'use a new numbered glibc preview tag')
    require(re.fullmatch(r'[0-9a-f]{40}', args.source_commit), 'source commit must be a full Git SHA')
    for name in ('base_archive', 'kit', 'system', 'sources'):
        setattr(args, name, getattr(args, name).resolve(strict=True))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    lock = load_json(LOCK)
    require(sha_file(args.base_archive) == lock['base_sha256'], 'Preview 2 archive SHA-256 mismatch')
    profile = load_json(args.kit / 'profile.json')
    require('cxx_runtime' in profile['features'], 'glibc C++ profile required')
    binding = verify_profile(profile, 'glibc', args.kit / 'sdk')
    metadata = load_json(args.kit / 'sdk/manifest.json')
    for name, expected in metadata['inputs'].items():
        require(sha_file(ROOT / name) == expected, 'SDK source differs from packaging checkout: ' + name)
    for name in APP_TOOLS:
        require(sha_file(args.kit / 'scripts' / name) == sha_file(ROOT / 'scripts' / name),
                'application kit tool differs: ' + name)
    system = load_json(args.system / 'manifest.json')
    for name, expected in system['sources'].items():
        require(sha_file(ROOT / name) == expected, 'system source differs from packaging checkout: ' + name)
    iso = args.system / 'xos-install.iso'
    require(sha_file(iso) == system['artifacts']['xos-install.iso']['sha256'], 'system ISO mismatch')
    name = args.tag + '-linux-x86_64'
    with tempfile.TemporaryDirectory(prefix='.host-sdk-', dir=output.parent) as temporary:
        stage = Path(temporary)
        source_root = stage / (args.tag + '-sources')
        source_root.mkdir()
        source = source_snapshot(source_root / 'xos')
        require(source['source_commit'] == args.source_commit, 'source commit differs from Git snapshot')
        for inputs in (metadata['inputs'], system['sources']):
            for filename, expected in inputs.items():
                require(source['files'].get(filename, {}).get('sha256') == expected,
                        'built input differs from committed source: ' + filename)
        upstream = source_root / 'upstream'
        upstream.mkdir()
        for filename in ('glibc-2.44.tar.xz', 'gcc-16.2.0.tar.xz',
                         'gcc-16.2.0.tar.xz.sig', 'gnu-keyring.gpg'):
            shutil.copy2(args.sources / filename, upstream / filename)
        glibc_auth = verify_glibc(upstream / 'glibc-2.44.tar.xz', source_root / 'glibc-verification')
        gcc_auth = verify_gcc(upstream / 'gcc-16.2.0.tar.xz', upstream / 'gcc-16.2.0.tar.xz.sig',
                              upstream / 'gnu-keyring.gpg', source_root / 'gcc-verification')
        source_binding = {'schema': 1, 'source_commit': args.source_commit,
                          'repository_files': source['files'], 'upstream': tree(upstream),
                          'glibc_verification': glibc_auth, 'gcc_verification': gcc_auth,
                          'host_tools': {'base_archive_sha256': lock['base_sha256'],
                                         'source_index': 'base-preview-2/SOURCES.md in the binary SDK'}}
        write_json(source_root / 'source-binding.json', source_binding)
        source_archive = output / (source_root.name + '.tar.zst')
        archive(source_root, source_archive)
        shutil.rmtree(source_root)

        # Extraction is permitted only after the exact released archive hash
        # matches. Its guest-root absolute symlinks are deliberately retained.
        subprocess.run(['tar', '--zstd', '-xf', str(args.base_archive), '-C', str(stage)], check=True)
        sdk = stage / lock['base_name']
        sdk.rename(stage / name)
        sdk = stage / name
        rootfs, xos = sdk / 'rootfs', sdk / 'rootfs/opt/xos'
        before = tree(rootfs, exclude=('opt/xos',))
        base = sdk / 'base-preview-2'
        base.mkdir()
        for file in list(sdk.iterdir()):
            if file.is_file() and file.name != 'xos-sdk':
                file.rename(base / file.name)
        legacy = xos / 'legacy/newlib'
        legacy.mkdir(parents=True)
        (xos / 'sysroot').rename(legacy / 'sdk')
        (xos / 'boot').rename(legacy / 'boot')
        (xos / 'bin/xos-sdk-smoke').rename(legacy / 'xos-sdk-smoke')
        shutil.copytree(args.kit, xos / 'glibc', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        require(tree_receipt(xos / 'glibc')[0] == tree_receipt(args.kit)[0], 'copied kit differs')
        (xos / 'sysroot').symlink_to('glibc/sdk/sysroot')
        (xos / 'bin/xos-app').symlink_to('../glibc/xos-app')
        (xos / 'boot').mkdir()
        shutil.copy2(iso, xos / 'boot/xos-install.iso')
        shutil.copy2(args.system / 'manifest.json', xos / 'boot/system-manifest.json')
        validation = xos / 'validation'
        for folder in ('scripts', 'tests', 'fixtures', 'bin'):
            (validation / folder).mkdir(parents=True)
        for relative in ('scripts/make_work_disk.py', 'scripts/run_qemu.py', 'tests/boot_smoke.py'):
            shutil.copy2(ROOT / relative, validation / relative)
        for suffix in ('c', 'cpp'):
            shutil.copy2(ROOT / 'docs/reports/glibc_stock_apps_20261126' / ('external.' + suffix),
                         validation / 'fixtures' / ('external.' + suffix))
        shutil.copy2(host_tool(), validation / 'bin/work_disk_host')
        shutil.copy2(ROOT / 'scripts/glibc_host_sdk_smoke.py', validation / 'smoke.py')
        smoke = xos / 'bin/xos-sdk-smoke'
        smoke.write_text('#!/bin/sh\nset -eu\nexec python3 /opt/xos/validation/smoke.py "$@"\n')
        smoke.chmod(0o755)
        launcher = (sdk / 'xos-sdk').read_text()
        old = '--setenv XOS_SDK /opt/xos/sysroot'
        require(launcher.count(old) == 1, 'unknown base launcher default')
        launcher = launcher.replace(old, '--setenv XOS_SDK /opt/xos/glibc/sdk/sysroot '
                                    '--setenv XOS_APP_KIT /opt/xos/glibc '
                                    '--setenv XOS_LEGACY_NEWLIB_SDK /opt/xos/legacy/newlib/sdk')
        (sdk / 'xos-sdk').write_text(launcher)
        (sdk / 'README.md').write_text((ROOT / 'docs/releases/glibc_host_sdk.md').read_text())
        (legacy / 'README.md').write_text(
            '# Preview 2 newlib SDK\n\nThis is the unchanged Preview 2 target SDK and boot image. '
            'Select its sysroot explicitly for existing newlib projects; keep their package profiles '
            'and disks separate. The default host SDK and xos-app now select glibc. '
            'This is not the original 1024 frozen rollback distribution.\n')
        require(tree(rootfs, exclude=('opt/xos',)) == before, 'inherited host files changed')
        release = {'schema': 1, 'tag': args.tag, 'source_commit': args.source_commit,
                   'base_sdk_sha256': lock['base_sha256'], 'host_files_unchanged': True,
                   'inherited_host_tree_sha256': receipt(before), 'inherited_host_file_count': len(before),
                   'application_kit_tree_sha256': tree_receipt(xos / 'glibc')[0],
                   'profile_sha256': sha_file(xos / 'glibc/profile.json'), 'binding': binding,
                   'system': {'build_id': system['build_id'], 'source_sha256': system['source_sha256'],
                              'manifest_sha256': sha_file(args.system / 'manifest.json'),
                              'iso_sha256': sha_file(iso)},
                   'source_archive': {'name': source_archive.name, 'sha256': sha_file(source_archive)},
                   'guest_qualification': 'requires fresh extracted archive consumer validation'}
        write_json(xos / 'host-sdk.json', release)
        write_json(sdk / 'host-sdk.json', release)
        write_json(sdk / 'file-manifest.json', tree(sdk))
        binary_archive = output / (name + '.tar.zst')
        archive(sdk, binary_archive)
        write_json(output / 'package.json', {**release, 'archive': {
            'name': binary_archive.name, 'sha256': sha_file(binary_archive)}})
    print(json.dumps({'status': 'packaged_guest_not_run', 'archive': binary_archive.name}))


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for field in ('base-archive', 'kit', 'system', 'sources', 'output'):
        parser.add_argument('--' + field, type=Path, required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--source-commit', required=True)
    package(parser.parse_args())


if __name__ == '__main__':
    main()
