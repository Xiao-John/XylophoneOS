#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Assemble or verify a local glibc application SDK release preview."""
import argparse
import json
from pathlib import Path
import shutil
import stat

from package_glibc_sdk import package_sdk
from xypm_format import canonical, require, sha_file
from xypm_sdk_profile import digest_value, metadata_snapshot, relative_file, sdk_snapshot, verify_profile


ROOT = Path(__file__).resolve().parents[1]
FROZEN_RELEASE = ROOT / 'docs/releases/release_0_0_1_1024.json'
FROZEN_PROFILE = ROOT / 'config/package/xos_x86_64_static_single_v1.json'
FROZEN_ARCHIVE = 'xylophoneos_revival_0.0.1-1024_sdk.tar.gz'
KIT = 'application-sdk'
ISO = 'xos-install.iso'
SYSTEM = 'system_manifest.json'
PREVIEW = 'application_preview.json'
ROLLBACK_PROFILE = 'rollback/profile.json'
ROLLBACK_ARCHIVE = f'rollback/{FROZEN_ARCHIVE}'
README = f'''# XOS application SDK release preview

Use `{KIT}/xos-app` and the included profile to build and pack glibc C and
C++ applications. See `{KIT}/README.md` for the required host tools and
example commands. Use `{ISO}` with a dedicated glibc package disk.

For newlib, keep the existing frozen system and its package disk. Extract
`{ROLLBACK_ARCHIVE}` into a separate directory and
select that SDK together with `{ROLLBACK_PROFILE}` when invoking the
application tools. Preserve the work disk from the same frozen profile
when switching back. Consult the release playbook for commands.

Assembly verifies the staged bytes and SDK profile. Guest acceptance and
default SDK selection are separate gates.
'''


def artifact(path):
    return {'bytes': path.stat().st_size, 'sha256': sha_file(path)}


def inspect_system(iso, manifest):
    system, manifest_hash = metadata_snapshot(manifest)
    build_id = system['build_id']
    require(isinstance(build_id, str) and build_id, 'system manifest lacks a build ID')
    source_hash = digest_value(system['source_sha256'], 'system source')
    image = artifact(iso)
    require(system['artifacts'][ISO] == image, 'system manifest does not bind the ordinary install ISO')
    return {'build_id': build_id, 'source_sha256': source_hash,
            'manifest_sha256': manifest_hash, 'iso': image}


def inspect_rollback(archive):
    release, _ = metadata_snapshot(FROZEN_RELEASE)
    asset = next((entry for entry in release['assets'] if entry['name'] == FROZEN_ARCHIVE), None)
    require(asset is not None, 'newlib SDK is absent from the frozen release record')
    receipt = artifact(archive)
    require(asset['digest'] == 'sha256:' + receipt['sha256'] and asset['size'] == receipt['bytes'],
            'newlib archive differs from the frozen release')
    profile, profile_hash = metadata_snapshot(FROZEN_PROFILE)
    require(release['system_build_id'] in profile['verified_system_builds'],
            'frozen system is absent from the newlib profile')
    return {'release_tag': release['tag'], 'system_build_id': release['system_build_id'],
            'profile_id': profile['id'], 'profile_sha256': profile_hash, 'archive': receipt}


def inspect_preview(root):
    require(root.is_dir() and not root.is_symlink(), 'preview must be a real directory')
    system = inspect_system(relative_file(root, ISO), relative_file(root, SYSTEM))
    rollback = inspect_rollback(relative_file(root, ROLLBACK_ARCHIVE))
    metadata_snapshot(relative_file(root, ROLLBACK_PROFILE), rollback['profile_sha256'])

    kit = root / KIT
    launcher = relative_file(root, f'{KIT}/xos-app')
    require(launcher.stat().st_mode & stat.S_IXUSR, 'glibc kit launcher is not executable')
    profile, profile_hash = metadata_snapshot(relative_file(root, f'{KIT}/profile.json'))
    require('cxx_runtime' in profile['features'], 'glibc preview requires both C and C++')
    binding = verify_profile(profile, 'glibc', kit / 'sdk')
    kit_tree_hash, _ = sdk_snapshot(kit)
    sdk = {'profile_id': binding['profile_id'], 'profile_sha256': profile_hash,
           'sdk_tree_sha256': binding['sdk_tree_sha256'],
           'sdk_manifest_sha256': profile['sdk_binding']['sdk_manifest_sha256'],
           'kit_tree_sha256': kit_tree_hash}
    return {'schema_version': 1, 'status': 'application_sdk_preview', 'guest_qualification': 'not_run',
            'readme_sha256': sha_file(relative_file(root, 'README.md')),
            'system': system, 'glibc_application_sdk': sdk, 'frozen_newlib': rollback}


def verify_preview(root):
    staged = inspect_preview(root)
    recorded, _ = metadata_snapshot(relative_file(root, PREVIEW))
    require(recorded == staged, 'preview manifest differs from staged components')
    return recorded


def assemble(output, iso, system_manifest, sdk, profile, frozen_sdk):
    system = inspect_system(iso, system_manifest)
    rollback = inspect_rollback(frozen_sdk)
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    try:
        kit = package_sdk(sdk, profile, output / KIT)
        (output / 'rollback').mkdir()
        shutil.copyfile(iso, output / ISO)
        shutil.copyfile(system_manifest, output / SYSTEM)
        shutil.copyfile(frozen_sdk, output / ROLLBACK_ARCHIVE)
        shutil.copyfile(FROZEN_PROFILE, output / ROLLBACK_PROFILE)
        (output / 'README.md').write_bytes(README.encode('utf-8'))
        preview = inspect_preview(output)
        require(preview['system'] == system and preview['frozen_newlib'] == rollback
                and preview['glibc_application_sdk']['kit_tree_sha256'] == kit['kit_tree_sha256'],
                'preview inputs changed during assembly')
        (output / PREVIEW).write_bytes(canonical(preview))
        return preview
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    stage = commands.add_parser('assemble', help='stage a preview in a fresh directory')
    stage.add_argument('--iso', type=Path, required=True)
    stage.add_argument('--system-manifest', type=Path, required=True)
    stage.add_argument('--glibc-sdk-build', type=Path, required=True)
    stage.add_argument('--glibc-profile', type=Path, required=True)
    stage.add_argument('--frozen-newlib-sdk', type=Path, required=True)
    stage.add_argument('--output', type=Path, required=True)
    verify = commands.add_parser('verify', help='recheck a staged preview')
    verify.add_argument('preview', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'assemble':
            receipt = assemble(args.output, args.iso, args.system_manifest,
                               args.glibc_sdk_build, args.glibc_profile, args.frozen_newlib_sdk)
        else:
            receipt = verify_preview(args.preview)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, 'application SDK preview: ' + str(error) + '\n')
    print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    main()
