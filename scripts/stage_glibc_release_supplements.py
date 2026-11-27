#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage a checksum list and verified supplements for a frozen glibc release."""

import argparse
from gzip import GzipFile
from pathlib import Path
import shutil
import tarfile
from tempfile import TemporaryDirectory

from package_application_preview import artifact
from package_glibc_gnu_seed import SOURCE_ARCHIVE
from package_glibc_release import MANIFEST, release_checksums, verify_archive_members
from package_glibc_release_sources import verify as verify_component_sources
from relink_release_xypm import FORMAT as RELINK_FORMAT
from xypm_format import canonical, confined, load_json, require, sha_file

CHECKSUMS = 'CHECKSUMS.sha256'
SOURCES = 'component-sources.tar.gz'
SOURCES_MANIFEST = 'component-sources.json'
RELINK = 'xypm-relink.tar.gz'
DISTRIBUTION = 'distribution_manifest.json'
SYSTEM = 'system_manifest.json'


def verify_base(root):
    manifest_path = confined(root, MANIFEST)
    release = load_json(manifest_path)
    require(release['schema_version'] == 1 and release['status'] == 'assembled_glibc_candidate',
            'expected an assembled glibc release candidate')
    archives = release['archives']
    require(set(archives) == {'images.tar.gz', 'application-sdk.tar.gz', 'packages.tar.gz', SOURCE_ARCHIVE}
            and 'gnu_seed' in release, 'expected the complete GNU Seed archive set')
    assets = {name: artifact(confined(root, name)) for name in (*archives, MANIFEST, SYSTEM)}
    require(all(assets[name] == value for name, value in archives.items())
            and assets[SYSTEM]['sha256'] == release['system']['manifest_sha256'],
            'frozen release asset differs')
    require(confined(root, CHECKSUMS).read_bytes() == release_checksums(root, release),
            'frozen release checksums differ')
    return release, assets


def stage_component_sources(root, output, expected, release_digest):
    source_manifest = confined(root, SOURCES_MANIFEST)
    source_archive = confined(root, SOURCES)
    require(sha_file(source_manifest) == expected, 'component sources manifest differs')
    receipt = load_json(source_manifest)
    require(receipt['binding']['release_manifest_sha256'] == release_digest,
            'component sources belong to a different release')
    shutil.copyfile(source_manifest, output / SOURCES_MANIFEST)
    shutil.copyfile(source_archive, output / SOURCES)
    verify_component_sources(argparse.Namespace(archive=output / SOURCES, manifest=output / SOURCES_MANIFEST,
                                                manifest_sha256=expected))


def stage_xypm_relink(root, output, expected, release, release_digest):
    manifest_path = confined(root, 'manifest.json')
    manifest = load_json(manifest_path)
    require(sha_file(manifest_path) == expected and manifest['format'] == RELINK_FORMAT,
            'xypm relink manifest differs')
    files = manifest['files']
    require('manifest.json' not in files and files['receipt/release_manifest.json'] == release_digest
            and files['receipt/sdk_manifest.json'] == release['application_sdk']['sdk_manifest_sha256']
            and manifest['reference'] == release['xypm_sha256'], 'xypm relink materials belong to a different release')
    digests = {'manifest.json': expected, **files}
    records = {}
    with output.open('xb') as raw, GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as packed, \
            tarfile.open(fileobj=packed, mode='w|', format=tarfile.USTAR_FORMAT) as archive:
        for name in sorted(digests):
            source = confined(root, name)
            records[name] = artifact(source)
            require(digests[name] == records[name]['sha256'], 'xypm relink file differs: ' + name)
            entry = tarfile.TarInfo(name)
            entry.size = records[name]['bytes']
            with source.open('rb') as stream:
                archive.addfile(entry, stream)
    verify_archive_members(output, records)


def stage(args):
    release, base_assets = verify_base(args.release)
    base_digest = base_assets[MANIFEST]['sha256']
    output = args.output.absolute()
    require(not output.exists() and not output.is_symlink(), 'choose a new supplement output')
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as directory:
        staging = Path(directory) / 'supplements'
        staging.mkdir()
        stage_component_sources(args.components, staging, args.component_manifest_sha256, base_digest)
        stage_xypm_relink(args.xypm_relink, staging / RELINK, args.xypm_manifest_sha256, release, base_digest)
        supplements = {name: artifact(staging / name) for name in (SOURCES, SOURCES_MANIFEST, RELINK)}
        receipt = {'format': 'xos_glibc_release_supplements_v1', 'release_manifest_sha256': base_digest,
                   'base_assets': base_assets, 'supplements': supplements,
                   'xypm_relink_manifest_sha256': args.xypm_manifest_sha256}
        (staging / DISTRIBUTION).write_bytes(canonical(receipt))
        assets = {**base_assets, **supplements, DISTRIBUTION: artifact(staging / DISTRIBUTION)}
        checksums = ''.join(f'{item["sha256"]}  {name}\n' for name, item in sorted(assets.items()))
        (staging / CHECKSUMS).write_text(checksums)
        staging.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('release', 'components', 'xypm-relink', 'output'):
        parser.add_argument('--' + flag, type=Path, required=True)
    for flag in ('component-manifest-sha256', 'xypm-manifest-sha256'):
        parser.add_argument('--' + flag, required=True)
    args = parser.parse_args()
    try:
        stage(args)
    except (OSError, ValueError, TypeError, KeyError, tarfile.TarError) as error:
        parser.exit(1, f'glibc release supplements: {error}\n')


if __name__ == '__main__':
    main()
