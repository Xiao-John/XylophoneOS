#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prepare isolated Qt/SDK overlays for the current-main SSG-P4A builds."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local_build_path(path):
    path = path.resolve()
    build = (root / 'build').resolve()
    if path != build and build not in path.parents:
        raise SystemExit('derived toolchain outputs must stay under this checkout build/')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-sdk', 'system-build', 'source-qt-build', 'output-sdk', 'output-qt-build'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    source_sdk, system_build, source_qt = [path.resolve(strict=True) for path in
        (args.source_sdk, args.system_build, args.source_qt_build)]
    output_sdk = local_build_path(args.output_sdk)
    output_qt = local_build_path(args.output_qt_build)
    if output_sdk.exists() or output_qt.exists():
        raise SystemExit('choose fresh output-sdk and output-qt-build directories')
    system_sdk = system_build / 'sdk'
    source_manifest_path = source_sdk / 'manifest.json'
    system_manifest_path = system_build / 'manifest.json'
    source_manifest = json.loads(source_manifest_path.read_text())
    system_manifest = json.loads(system_manifest_path.read_text())

    output_sdk.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_sdk, output_sdk)
    current_xos = system_sdk / 'include/xos'
    target_xos = output_sdk / 'include/xos'
    shutil.copytree(current_xos, target_xos, dirs_exist_ok=True)

    current_file_client_object = system_build / 'src_user_sdk_file_client.cpp.o'
    if not current_file_client_object.is_file():
        raise SystemExit('current-main build is missing its compiled file_client object')
    overlay_object = output_sdk / 'objects' / current_file_client_object.name
    overlay_object.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(current_file_client_object, overlay_object)
    archive = output_sdk / 'lib/libxos.a'
    ar = shutil.which('x86_64-elf-ar')
    if not ar:
        raise SystemExit('missing x86_64-elf-ar')
    members = subprocess.check_output([ar, 't', str(archive)], text=True).splitlines()
    if members.count(overlay_object.name) != 1:
        raise SystemExit('expected exactly one replaceable file_client member; rebuild the SDK')
    subprocess.run([ar, 'rcsD', str(archive), str(overlay_object)], check=True)

    manifest_path = output_sdk / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    artifact_paths = set(manifest.get('artifacts', {}))
    for header in target_xos.rglob('*'):
        if not header.is_file():
            continue
        relative = header.relative_to(output_sdk).as_posix()
        artifact_paths.add(relative)
    artifact_paths.add('lib/libxos.a')
    artifact_paths.add(overlay_object.relative_to(output_sdk).as_posix())
    inherited_provenance = manifest.pop('archive_provenance', None)
    manifest['qualification'] = 'not_run'
    manifest['archive_provenance_pending'] = 'mixed legacy overlay; rebuild the complete SDK before qualification or distribution'
    artifacts = {}
    for relative in sorted(artifact_paths):
        artifact = output_sdk / relative
        if not artifact.is_file():
            raise SystemExit('missing inherited SDK artifact: ' + relative)
        artifacts[relative] = sha(artifact)
    manifest['artifacts'] = artifacts
    manifest['p4a_derived_overlay'] = {
        'source_sdk_manifest_sha256': sha(source_manifest_path),
        'current_main_system_manifest_sha256': sha(system_manifest_path),
        'current_main_file_client_header_sha256': sha(current_xos / 'file_client.hpp'),
        'current_main_file_client_object_sha256': sha(current_file_client_object),
        'archive_replacement': overlay_object.relative_to(output_sdk).as_posix(),
        'inherited_archive_provenance_invalidated': inherited_provenance is not None,
        'intent': 'retain the qualified Qt E17 C++ runtime while supplying current-main file::client symbols',
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

    output_qt.parent.mkdir(parents=True, exist_ok=True)
    output_qt.mkdir()
    cache_path = source_qt / 'CMakeCache.txt'
    cache = cache_path.read_text()
    if str(source_sdk) not in cache:
        raise SystemExit('Qt build cache does not reference the supplied source SDK')
    for entry in source_qt.iterdir():
        destination = output_qt / entry.name
        if entry.name == 'CMakeCache.txt':
            destination.write_text(cache.replace(str(source_sdk), str(output_sdk)))
        else:
            destination.symlink_to(entry, target_is_directory=entry.is_dir())
    receipt = {
        'status': 'PREPARED',
        'source_sdk_manifest_sha256': sha(source_manifest_path),
        'source_system_manifest_sha256': sha(system_manifest_path),
        'derived_sdk_manifest_sha256': sha(manifest_path),
        'derived_libxos_sha256': sha(archive),
        'qt_cache_source_sha256': sha(cache_path),
        'qt_cache_overlay_sha256': sha(output_qt / 'CMakeCache.txt'),
        'compiler_version': subprocess.check_output([shutil.which('x86_64-elf-g++'), '--version'],
                                                    text=True).splitlines()[0],
        'archive_member': overlay_object.relative_to(output_sdk).as_posix(),
        'semantics': 'local build overlay; no installed SDK or Qt artifact changed',
    }
    (output_sdk / 'p4a_overlay_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('prepared current-main SSG-P4A SDK and Qt overlays')
    print('sdk_manifest_sha256=' + sha(manifest_path))
    print('libxos_sha256=' + sha(archive))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
