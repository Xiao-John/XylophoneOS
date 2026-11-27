#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the published 0.0.2-1103 Seed binaries against their source records."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import tarfile

from prepare_glibc_gnu_seed import FROZEN, TOOLS
from xypm_format import canonical, load_json, require, sha_file
from xypm_sdk_profile import relative_file

SEED_RECORD = 'build_records/cpp_bundle_seed_manifest.json'
CORRESPONDENCE = (
    'unchanged_gnu_correspondence/xos-0.0.1-1024-gnu-sources.tar.gz',
    'unchanged_gnu_correspondence/xos-0.0.1-1024-gnu-source-supplement-gxx-lrealpath.tar.gz',
)


def verify(folder, *, material_root=None):
    frozen = load_json(FROZEN)
    assets = {record['name']: record for record in frozen['assets']}
    folder_name = 'xos-' + frozen['version'] + '-sources'
    source_asset = relative_file(folder, folder_name + '.tar.gz')
    release_path = relative_file(folder, 'release_manifest.json')
    for path in (source_asset, release_path):
        expected = assets[path.name]
        require(path.stat().st_size == expected['bytes'] and sha_file(path) == expected['sha256'],
                'published source/receipt bytes differ: ' + path.name)
    release = load_json(release_path)
    with tarfile.open(source_asset, 'r:gz') as archive:
        member_prefix = folder_name + '/'
        with archive.extractfile(member_prefix + 'source_manifest.json') as stream:
            manifest = json.load(stream)
        require(manifest['source_commit'] == frozen['source_commit'], 'frozen source commit differs')
        inventory = {item['path']: item for item in manifest['records']}
        for name in (SEED_RECORD, *CORRESPONDENCE):
            entry = archive.getmember(member_prefix + name)
            expected = inventory[name]
            require(entry.isfile() and entry.size == expected['bytes'],
                    'frozen correspondence size differs: ' + name)
            with archive.extractfile(entry) as stream:
                if material_root is None:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                else:
                    output = material_root / name
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with output.open('xb') as dest:
                        shutil.copyfileobj(stream, dest, 1 << 20)
                    digest = sha_file(output)
                require(digest == expected['sha256'], 'frozen correspondence bytes differ: ' + name)
        require(inventory[SEED_RECORD]['sha256'] == release['seed_manifest_sha256'],
                'source and release name different GNU Seed build manifests')
        with archive.extractfile(member_prefix + SEED_RECORD) as stream:
            seed = json.load(stream)

    installed = {entry['guest_path']: entry['sha256'] for entry in seed['install_files']}
    tools = {name: release['guest_files'][name] for name in TOOLS}
    require(all(digest == installed.get(name) for name, digest in tools.items()),
            'frozen tools differ from the matching source build record')
    return {'status': 'verified_frozen_correspondence', 'source_commit': frozen['source_commit'],
            'source_asset_sha256': assets[source_asset.name]['sha256'],
            'release_manifest_sha256': assets[release_path.name]['sha256'],
            'build_manifest_sha256': release['seed_manifest_sha256'],
            'artifacts': {name: inventory[name] for name in CORRESPONDENCE}, 'tools': tools}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--donor-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = canonical(verify(args.donor_dir))
        with args.output.open('xb') as stream:
            stream.write(result)
    except (OSError, ValueError, KeyError, tarfile.TarError) as error:
        parser.exit(1, 'GNU Seed source correspondence failed: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
