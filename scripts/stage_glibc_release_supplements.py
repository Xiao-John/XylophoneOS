#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage a checksum list and verified supplements for a frozen glibc release."""

import argparse
from gzip import GzipFile
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
from tempfile import TemporaryDirectory

from package_application_preview import artifact
from package_glibc_gnu_seed import SOURCE_ARCHIVE
from package_glibc_release import KIT, MANIFEST, release_checksums, verify_archive_members
from package_glibc_release_sources import verify as verify_component_sources
from relink_release_daily import FORMAT as DAILY_FORMAT
from relink_release_xypm import DASH_FORMAT, FORMAT as RELINK_FORMAT
from verify_glibc_source import PORT as GLIBC_PORT, verify_source
from xypm_format import canonical, confined, load_json, require, sha_file
from xypm_sdk_profile import source_binding

CHECKSUMS = 'CHECKSUMS.sha256'
SOURCES = 'component-sources.tar.gz'
SOURCES_MANIFEST = 'component-sources.json'
RELINK = 'xypm-relink.tar.gz'
DASH_RELINK = 'dash-relink.tar.gz'
DAILY_RELINK = 'daily-relink.tar.gz'
DISTRIBUTION = 'distribution_manifest.json'
SYSTEM = 'system_manifest.json'
SDK_ARCHIVE = 'application-sdk.tar.gz'
GLIBC_PORT_IN_SYSROOT = 'usr/share/xos-glibc/port'


def verify_base(root):
    manifest_path = confined(root, MANIFEST)
    release = load_json(manifest_path)
    require(release['schema_version'] == 1 and release['status'] == 'assembled_glibc_candidate',
            'expected an assembled glibc release candidate')
    archives = release['archives']
    require(set(archives) == {'images.tar.gz', SDK_ARCHIVE, 'packages.tar.gz', SOURCE_ARCHIVE}
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


def stage_relink_archive(source, output, expected, identity, bindings):
    shutil.copyfile(source, output)
    with tarfile.open(output, 'r:gz') as archive:
        entry = archive.getmember('manifest.json')
        require(entry.isfile() and entry.size <= 1024 * 1024, 'invalid relink manifest')
        with archive.extractfile(entry) as stream:
            data = stream.read()
        require(hashlib.sha256(data).hexdigest() == expected, 'relink manifest differs')
        manifest = json.loads(data)
        files = manifest['files']
        require('manifest.json' not in files
                and all(manifest.get(name) == value for name, value in identity.items())
                and all(files.get(name) == digest for name, digest in bindings.items()),
                'relink materials belong to a different release')
        records = {name: {'bytes': archive.getmember(name).size, 'sha256': digest}
                   for name, digest in files.items()}
        records['manifest.json'] = {'bytes': entry.size, 'sha256': expected}
    verify_archive_members(output, records)
    return files


def stage_glibc_source(sdk_archive, source, staging, sdk_manifest_sha256):
    lock = load_json(GLIBC_PORT / 'source_lock.json')
    trust = lock['signer_trust']
    port = 'sysroot/' + GLIBC_PORT_IN_SYSROOT
    signature = port + '/' + trust['signature_file']
    key = port + '/' + trust['key_file']
    selected = {'manifest.json', port + '/source_lock.json', signature, key}
    selected.update('source_verification/' + name for name in
                    ('report.json', 'gpgv.status', 'gpgv.log', 'release_key.gpg'))
    prefix = KIT + '/sdk/'
    with TemporaryDirectory(dir=staging.parent) as directory:
        sdk = Path(directory)
        seen = set()
        with tarfile.open(sdk_archive, 'r|gz') as archive:
            for member in archive:
                if not member.name.startswith(prefix):
                    continue
                name = member.name.removeprefix(prefix)
                if name not in selected:
                    continue
                require(name not in seen and member.isfile() and member.size <= 1024 * 1024,
                        'invalid glibc source metadata member: ' + name)
                target = sdk / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as input_file, target.open('xb') as output:
                    shutil.copyfileobj(input_file, output)
                seen.add(name)
        require(seen == selected, 'release SDK glibc source metadata is incomplete')
        manifest = sdk / 'manifest.json'
        require(sha_file(manifest) == sdk_manifest_sha256, 'release SDK manifest differs')
        binding, recorded_lock = source_binding(sdk, sdk / 'sysroot', load_json(manifest))
        require(recorded_lock == lock, 'release SDK does not match the reviewed glibc source lock')
        require(source.stat().st_size == lock['archive_bytes'], 'glibc source size differs from source lock')
        name = lock['archive']
        output = staging / name
        shutil.copyfile(source, output)
        verified = verify_source(output, sdk / 'fresh_verification', sdk / signature, sdk / key)
        require(verified['archive_sha256'] == binding['archive_sha256']
                and verified['lock_sha256'] == binding['source_lock_sha256'],
                'staged glibc source differs from the release SDK')
    return {'archive': name, 'sdk_manifest_sha256': sdk_manifest_sha256,
            'sdk_source_verification_report_sha256': binding['report_sha256'],
            'source_lock_sha256': binding['source_lock_sha256'],
            'signature_sha256': binding['signature_sha256'], 'key_sha256': binding['key_sha256'],
            'signer_primary_fingerprint': binding['primary_fingerprint'],
            'signer_fingerprint': binding['signing_fingerprint']}


def stage(args):
    release, base_assets = verify_base(args.release)
    base_digest = base_assets[MANIFEST]['sha256']
    sdk = release['application_sdk']
    relink_bindings = {'receipt/release_manifest.json': base_digest,
                       'receipt/sdk_manifest.json': sdk['sdk_manifest_sha256'],
                       'receipt/profile.json': sdk['profile_file_sha256']}
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
        if args.glibc_source is not None:
            source = stage_glibc_source(confined(args.release, SDK_ARCHIVE), args.glibc_source,
                                        staging, release['application_sdk']['sdk_manifest_sha256'])
            supplements[source['archive']] = artifact(staging / source['archive'])
            receipt.update(format='xos_glibc_release_supplements_v2', glibc_source=source)
        if args.dash_relink is not None:
            dash = stage_relink_archive(
                args.dash_relink, staging / DASH_RELINK, args.dash_manifest_sha256,
                {'format': DASH_FORMAT, 'reference': release['dash_sha256']},
                {**relink_bindings, 'receipt/install_manifest.json': release['installer_manifest_sha256']},
            )
            supplements[DASH_RELINK] = artifact(staging / DASH_RELINK)
            receipt.update(format='xos_glibc_release_supplements_v3',
                           dash_relink_manifest_sha256=args.dash_manifest_sha256,
                           dash_build_receipt_sha256=dash['receipt/dash.json'])
        if args.daily_relink is not None:
            daily = stage_relink_archive(
                args.daily_relink, staging / DAILY_RELINK, args.daily_manifest_sha256,
                {'format': DAILY_FORMAT, 'daily_xpk_sha256': release['daily_sha256']}, relink_bindings,
            )
            supplements[DAILY_RELINK] = artifact(staging / DAILY_RELINK)
            receipt.update(format='xos_glibc_release_supplements_v4',
                           daily_relink_manifest_sha256=args.daily_manifest_sha256,
                           daily_build_receipt_sha256=daily['receipt/daily.json'])
        (staging / DISTRIBUTION).write_bytes(canonical(receipt))
        assets = {**base_assets, **supplements, DISTRIBUTION: artifact(staging / DISTRIBUTION)}
        checksums = ''.join(f'{item["sha256"]}  {name}\n' for name, item in sorted(assets.items()))
        (staging / CHECKSUMS).write_text(checksums)
        staging.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('release', 'components', 'xypm-relink', 'output'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--glibc-source', type=Path, help='stage and authenticate the pinned upstream glibc source')
    for name in ('dash', 'daily'):
        parser.add_argument('--' + name + '-relink', type=Path)
        parser.add_argument('--' + name + '-manifest-sha256')
    for flag in ('component-manifest-sha256', 'xypm-manifest-sha256'):
        parser.add_argument('--' + flag, required=True)
    args = parser.parse_args()
    for name in ('dash', 'daily'):
        if (getattr(args, name + '_relink') is None) != (getattr(args, name + '_manifest_sha256') is None):
            parser.error(f'--{name}-relink and --{name}-manifest-sha256 are required together')
    try:
        stage(args)
    except (OSError, ValueError, TypeError, KeyError, tarfile.TarError) as error:
        parser.exit(1, f'glibc release supplements: {error}\n')


if __name__ == '__main__':
    main()
