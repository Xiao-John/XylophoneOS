#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate the real Mobius glibc package lifecycle with a legacy desktop on disk."""

import hashlib
import argparse
from pathlib import Path
import sys
import tempfile

from mobius_glibc_guest import run_mobius

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from make_work_disk import create_fat32
from xos_app import application_sdk_check, sdk_notices
from xypm_format import (DEFAULT_PROFILE, canonical, inspect_elf, load_json,
                         require, sha_file, verify_package)
from xypm_image import Disk, query_image, transact

PACKAGE_ID = 'xos.mobius'
EXECUTABLES = {'usr/bin/mobius.elf': 'mobius.elf',
               'usr/bin/mobius-session.elf': 'mobius_session.elf'}
LEGACY = '/bin/desktop.elf'
PREFERENCES = '/usr/share/xos.mobius/appearance.txt'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'target', 'package', 'legacy', 'legacy-receipt',
                 'profile', 'sdk-build', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True)
    profile = load_json(args.profile)
    require(profile.get('runtime_family') == 'glibc', 'Mobius test needs a glibc package profile')
    binding = application_sdk_check(args.sdk_build, profile)
    profile_sha = hashlib.sha256(canonical(profile)).hexdigest()
    image = args.system / 'xos-install.iso'
    system_manifest = args.system / 'manifest.json'
    metadata = load_json(system_manifest)
    require(sha_file(image) == metadata['artifacts']['xos-install.iso']['sha256'], 'system ISO mismatch')
    legacy_sha = sha_file(args.legacy)
    require(load_json(args.legacy_receipt)['elf_sha256'] == legacy_sha, 'legacy executable differs from its receipt')
    inspect_elf(args.legacy)
    package = verify_package(args.package, profile)
    manifest = package['manifest']
    files = {part['path']: part for part in manifest['files']}
    require(manifest['id'] == PACKAGE_ID, 'unexpected Mobius package ID')
    require({name for name, part in files.items() if part['role'] == 'executable'} == set(EXECUTABLES),
            'incorrect Mobius installed paths')
    payloads = {}
    for name, binary in EXECUTABLES.items():
        elf = args.target / binary
        receipt = elf.with_suffix('.receipt.json')
        digest = sha_file(elf)
        require(files[name]['sha256'] == digest == load_json(receipt)['elf_sha256'],
                f'package payload differs from built ELF: {name}')
        payloads[name] = {'elf_sha256': digest, 'build_receipt_sha256': sha_file(receipt)}
    for notice, name in sdk_notices(args.sdk_build, profile, 'cpp'):
        destination = f'usr/share/licenses/{PACKAGE_ID}/sdk/{name}'
        require(destination in manifest['licenses'] and files[destination]['sha256'] == sha_file(notice),
                f'glibc notice absent or changed: {name}')
    require(f'usr/share/licenses/{PACKAGE_ID}/NEWLIB-COPYING' not in files, 'foreign libc notice in glibc XPK')
    evidence = {'status': 'FAILED', 'package_sha256': package['sha256'], 'profile_sha256': profile_sha,
                'sdk_binding': binding, 'system_build_id': metadata['build_id'],
                'system_manifest_sha256': sha_file(system_manifest), 'image_sha256': sha_file(image),
                'legacy_sha256': legacy_sha, 'legacy_receipt_sha256': sha_file(args.legacy_receipt),
                'payloads': payloads, 'transactions': [], 'checks': []}
    try:
        with tempfile.TemporaryDirectory(prefix='xos_mobius_package_') as temp:
            work = Path(temp)
            source = work / 'old.img'
            preferences = work / 'appearance.txt'
            preferences.write_bytes(b'User-managed appearance preferences in the old work disk.\n')
            create_fat32(source, 512)
            with Disk(source, work) as disk:
                for path in ('/bin', '/usr', '/usr/bin', '/usr/share', '/usr/share/xos.mobius'):
                    disk.command('mkdir', path)
                disk.command('import', LEGACY, args.legacy)
                disk.command('import', PREFERENCES, preferences)
            source_sha = sha_file(source)
            evidence['source_sha256'] = source_sha

            wrong = work / 'wrong_profile.img'
            try:
                transact(source, wrong, load_json(DEFAULT_PROFILE), 'install', package=args.package)
            except ValueError as error:
                require('target profile mismatch' in str(error), 'wrong profile failed for an unexpected reason')
            else:
                raise AssertionError('frozen newlib profile accepted the glibc Mobius XPK')
            require(not wrong.exists() and sha_file(source) == source_sha, 'profile rejection changed source')
            evidence['checks'].append('newlib_profile_rejected')

            installed = work / 'installed.img'
            installed_receipt = transact(source, installed, profile, 'install', package=args.package)
            evidence['transactions'].append(installed_receipt)
            require(query_image(installed, profile, 'verify-installed')['files'] == len(files),
                    'installed package inventory disagrees with the manifest')
            with Disk(installed, work, True) as disk:
                receipt = load_json(disk.export('/' + manifest['build_receipt']['path']))
                require(receipt['elfs'] == payloads and receipt['sdk_manifest_sha256'] == binding['sdk_manifest_sha256']
                        and receipt['sdk_tree_sha256'] == binding['tree_sha256']
                        and receipt['profile_sha256'] == profile_sha, 'installed product receipt mismatch')
                require(sha_file(disk.export(LEGACY)) == legacy_sha, 'install changed the legacy desktop')
                require(sha_file(disk.export(PREFERENCES)) == sha_file(preferences),
                        'install changed the old preferences')
            installed_logs = output / 'installed'
            installed_logs.mkdir()
            evidence['installed'] = {}
            run_mobius(image, installed, installed_logs, evidence['installed'])
            evidence['checks'].append('installed_desktop_and_session_guest')

            removed = work / 'removed.img'
            evidence['transactions'].append(transact(installed, removed, profile, 'remove', package_id=PACKAGE_ID))
            require(query_image(removed, profile, 'verify-installed')['files'] == 0,
                    'managed files remain after Mobius removal')
            with Disk(removed, work, True) as disk:
                for name in files:
                    require(disk.info('/' + name) is None, f'package unlink left {name}')
                require(sha_file(disk.export(LEGACY)) == legacy_sha, 'removal changed the legacy desktop')
                require(sha_file(disk.export(PREFERENCES)) == sha_file(preferences),
                        'removal changed the old preferences')
            legacy_logs = output / 'removed'
            legacy_logs.mkdir()
            evidence['removed'] = {}
            run_mobius(image, removed, legacy_logs, evidence['removed'],
                       launchers=(('legacy', 'exec-file ' + LEGACY),))
            require(sha_file(source) == source_sha, 'package lifecycle changed the original disk')
            evidence['checks'].append('removed_package_legacy_desktop_and_preferences_preserved')
            evidence['status'] = 'PASSED'
    except Exception as error:
        evidence['error'] = str(error)
        raise
    finally:
        (output / 'report.json').write_bytes(canonical(evidence))


if __name__ == '__main__':
    main()
