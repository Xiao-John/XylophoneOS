# SPDX-License-Identifier: Apache-2.0
"""Audit the retained 960fce43 distribution using already reopened inputs."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

from cpython_glibc_xpk_guest import package_receipt
from build_candidate import inspect_app_kit
from package_application_preview import artifact
from package_glibc_gnu_seed import MATERIALS_DIR, check_archive, verify_materials
from package_glibc_release import verify_archive_members
from prepare_glibc_gnu_seed import MAKE_PATH, TOOLS
from relink_release_xypm import FORMAT as RELINK_FORMAT
from xos_bundle import parse as parse_bundle
from xypm_format import inspect_elf, load_json, sha_file, verify_package
from xypm_image import Disk, query_image
from xypm_sdk_profile import metadata_snapshot

parser = argparse.ArgumentParser(description=__doc__)
for name in ('retained', 'reopened', 'proof-dir', 'system', 'python-signature-receipt', 'scratch'):
    parser.add_argument('--' + name, type=Path, required=True)
parser.add_argument('--glibc-source', type=Path)
args = parser.parse_args()
if not __debug__:
    parser.error('run with Python assertions enabled')
assets, reopened, current_proof = args.retained, args.reopened, args.proof_dir
dist_path = assets / 'distribution_manifest.json'
dist, dist_sha = metadata_snapshot(dist_path, '1a086c10226b56e239143ddeda30569537c758582eb8d9a3598ced5232b09fdc')
release, release_sha = metadata_snapshot(assets / 'release_manifest.json', dist['release_manifest_sha256'])
expected_assets = dist['base_assets'] | dist['supplements'] | {dist_path.name: artifact(dist_path)}
assert all(artifact(assets / name) == val for name, val in expected_assets.items())
assert (assets / 'CHECKSUMS.sha256').read_text() == ''.join(
    f'{item["sha256"]}  {name}\n' for name, item in sorted(expected_assets.items()))
assert release['candidate_source_commit'] == '960fce4347f193f13f5214caee153a03891ab100'
assert sha_file(reopened / 'release_manifest.json') == release_sha
assert sha_file(assets / 'system_manifest.json') == release['system']['manifest_sha256']

kit = reopened / 'application-sdk'
profile, profile_sha = metadata_snapshot(kit / 'profile.json', release['application_sdk']['profile_file_sha256'])
assert inspect_app_kit(kit) == release['application_sdk']
glibc_path = 'application-sdk/sdk/sysroot/usr/share/xos-glibc/'
with tarfile.open(assets / 'application-sdk.tar.gz', 'r:gz') as archive:
    sdk_names = {x.name for x in archive if x.isfile()}
    sdk_license_names = {name for name in sdk_names if name.startswith(glibc_path) and
                         ('/licenses/' in name or 'COPYING' in name or name.endswith('/LICENSES'))}
    source_lock = json.load(archive.extractfile(glibc_path + 'port/source_lock.json'))
    gcc_lock = json.load(archive.extractfile(glibc_path + 'cxx/port/source_lock.json'))
    signed_report = json.load(archive.extractfile('application-sdk/sdk/source_verification/report.json'))
    signature = archive.extractfile(glibc_path + 'port/' + source_lock['signer_trust']['signature_file'])
    key = archive.extractfile(glibc_path + 'port/' + source_lock['signer_trust']['key_file'])
    assert hashlib.file_digest(signature, 'sha256').hexdigest() == source_lock['signature_sha256']
    assert hashlib.file_digest(key, 'sha256').hexdigest() == source_lock['signer_trust']['key_sha256']
    assert sdk_license_names
assert source_lock['version'] == '2.44' and signed_report['status'] == 'upstream_signature_verified'
assert signed_report['archive_sha256'] == source_lock['archive_sha256']
if args.glibc_source:
    assert artifact(args.glibc_source) == {
        'sha256': source_lock['archive_sha256'], 'bytes': source_lock['archive_bytes']}

images = reopened / 'images'
disk_path = images / 'work_disk.img'
assert artifact(disk_path) == release['work_disk']
assert artifact(images / 'xos-install-dash.iso') == release['installer_iso']
assert sha_file(images / 'install_manifest.json') == release['installer_manifest_sha256']
seed, seed_sha = metadata_snapshot(images / 'gnu_seed_receipt.json', release['gnu_seed']['receipt']['sha256'])
assert seed['work_disk_sha256'] == release['work_disk']['sha256'] and seed['system'] == release['system']
assert seed['packages'] == release['packages'] and seed['sdk'] == release['application_sdk']
seed_material = check_archive(assets / 'gnu-seed-sources.tar.gz', release['gnu_seed']['sources_manifest'])
verify_materials(seed_material, seed['installed_files'], seed['sdk'])
assert set(seed_material['frozen']['tools']) == set(TOOLS)
sig = load_json(current_proof / 'gnu-seed-signature-receiver.json')
assert sig['status'] == 'passed' and sig['release_manifest_sha256'] == release_sha
assert sig['source_archive_sha256'] == release['archives']['gnu-seed-sources.tar.gz']['sha256']
assert sig['gnu_make_signer'] == seed_material['make']['source_verified_signer']
assert sig['gnu_make_inputs'] == len(seed_material['make']['inputs'])
# Inspect the old corresponding-source bundles in the current asset directly,
# including the GCC archive reused by the SDK, without extracting either bundle.
nested_gnu_archives = {}
gcc_source = None
with tarfile.open(assets / 'gnu-seed-sources.tar.gz', 'r|gz') as outer:
    for member in outer:
        if not member.isfile() or 'unchanged_gnu_correspondence/' not in member.name:
            continue
        with tarfile.open(fileobj=outer.extractfile(member), mode='r|gz') as archive:
            for item in archive:
                name = Path(item.name).name
                if item.isfile() and name.endswith(('.tar.xz', '.tar.gz', '.tar.bz2')):
                    nested_gnu_archives[name] = item.size
                    if name == gcc_lock['source_archive']:
                        gcc_source = hashlib.file_digest(archive.extractfile(item), 'sha256').hexdigest()
assert gcc_source == gcc_lock['sha256']

components, components_sha = metadata_snapshot(assets / 'component-sources.json',
                                              expected_assets['component-sources.json']['sha256'])
assert components['binding']['release_manifest_sha256'] == release_sha
assert bool(components['records'])
assert components['archive'] == expected_assets['component-sources.tar.gz']
verify_archive_members(assets / 'component-sources.tar.gz', components['records'])
component_archive = assets / 'component-sources.tar.gz'
with tarfile.open(component_archive, 'r:gz') as archive:
    frozen_receipts = {name: json.load(archive.extractfile('receipts/' + name + '.json'))
                       for name in ('dash', 'daily_build', 'cpython_build', 'cpython_cli',
                                    'zlib', 'wheel_build', 'cpython_package', 'daily_package', 'wheel_package')}
assert frozen_receipts['dash']['sha256'] == release['dash_sha256']

with tarfile.open(assets / 'xypm-relink.tar.gz', 'r:gz') as archive:
    relink_names = {name.name: name.size for name in archive if name.isfile()}
    relink = json.load(archive.extractfile('manifest.json'))
assert relink['format'] == RELINK_FORMAT and relink['reference'] == release['xypm_sha256']
assert relink['files']['receipt/release_manifest.json'] == release_sha
assert relink['files']['receipt/sdk_manifest.json'] == release['application_sdk']['sdk_manifest_sha256']
assert set(relink_names) == (set(relink['files']) | {'manifest.json'})
verify_archive_members(assets / 'xypm-relink.tar.gz', {name: {'sha256': digest, 'bytes': relink_names[name]}
    for name, digest in (relink['files'] | {'manifest.json': dist['xypm_relink_manifest_sha256']}).items()})
for entries in (sdk_names, components['records'], seed_material['files'], relink_names, nested_gnu_archives):
    assert {'glibc_2_44.tar.xz', source_lock['archive']}.isdisjoint(Path(name).name for name in entries)

pkgs = {}
for label in release['packages']:
    src = reopened / 'packages' / (label + '.xpk')
    pkg = verify_package(src, profile, expected_sha256=release['packages'][label]['sha256'])
    manifest = pkg['manifest']
    assert manifest == frozen_receipts[label + '_package']
    pkgs[label] = {
        'id': manifest['id'], 'version': manifest['upstream_version'], 'revision': manifest['revision'],
        'xpk_sha256': pkg['sha256'], 'license_files': manifest['licenses'],
        'executables': [{'path': '/' + entry['path'], 'sha256': entry['sha256']}
                        for entry in manifest['files'] if entry['role'] == 'executable'],
        'receipt_sha256': manifest['build_receipt']['sha256'],
    }
cp, cp_receipt = package_receipt(reopened / 'packages/cpython.xpk', profile)
assert cp_receipt == frozen_receipts['cpython_build']
assert cp_receipt['zlib']['build_receipt_sha256'] == components['records']['receipts/zlib.json']['sha256']
assert cp_receipt['cli_build_receipt_sha256'] == components['records']['receipts/cpython_cli.json']['sha256']
assert cp_receipt['zlib']['artifacts']['lib/libz.a'] == frozen_receipts['zlib']['libz_sha256']
assert cp_receipt['source_archive_sha256'] == components['records']['archives/Python-3.14.9.tar.xz']['sha256']
python_signature = load_json(args.python_signature_receipt)
assert python_signature['status'] == 'upstream_signature_verified'
assert python_signature['materials']['Python-3.14.9.tar.xz'] == components['records']['archives/Python-3.14.9.tar.xz']
assert frozen_receipts['wheel_build']['wheel_sha256'] == components['records']['archives/idna-3.20-py3-none-any.whl']['sha256']
assert not pkgs['wheel']['executables']
pkgs['cpython']['static_extensions'] = frozen_receipts['cpython_cli']['static_extensions']
pkgs['cpython']['stdlib_members'] = len(cp_receipt['library']['members'])
pkgs['cpython']['libz_sha256'] = frozen_receipts['zlib']['libz_sha256']
pkgs['wheel']['upstream_wheel_sha256'] = frozen_receipts['wheel_build']['wheel_sha256']

def iso_member(path, wanted):
    block = 2048
    image = path.read_bytes()
    primary = image[16 * block:17 * block]
    assert primary[1:6] == b'CD001'
    extent = int.from_bytes(primary[158:162], 'little')
    length = int.from_bytes(primary[166:170], 'little')
    root = image[extent * block:extent * block + length]
    at = 0
    while at < len(root):
        size = root[at]
        if not size:
            at = (at // block + 1) * block
            continue
        entry = root[at:at + size]
        name = entry[33:33 + entry[32]].split(b';')[0]
        if name == wanted:
            start = int.from_bytes(entry[2:6], 'little') * block
            return image[start:start + int.from_bytes(entry[10:14], 'little')]
        at += size
    raise ValueError('ISO member missing')

installer = load_json(images / 'install_manifest.json')
bundle = iso_member(images / 'xos-install-dash.iso', b'DASH.ELF')
assert hashlib.sha256(bundle).hexdigest() == installer['boot_bundle']['container_sha256']
members = parse_bundle(bundle)['members']
expected = {(1, 'dash'): release['dash_sha256'], (3, 'daily'): release['daily_sha256'],
            (5, 'xypm'): release['xypm_sha256']}
assert {(i['type'], i['name']): i['sha256'].hex() for i in members} == expected
boot_apps = {m['name']: m['sha256'].hex() for m in members if m['type'] != 3}
assert {r['id']: r['sha256'] for r in query_image(disk_path, profile)['packages']} == {
    item['id']: item['xpk_sha256'] for item in pkgs.values()}

nm = shutil.which('x86_64-elf-nm')
assert nm
def static_receipt(path, expected, family):
    assert sha_file(path) == expected
    kind = inspect_elf(path)
    assert kind['format'] == 'static_elf64'
    symbols = subprocess.check_output([nm, '--defined-only', path], stderr=subprocess.STDOUT, text=True)
    markers = [s for s in ('__libc_start_main', '_impure_ptr', '__getreent')
               if re.search(r'\s' + re.escape(s) + r'$', symbols, flags=re.MULTILINE)]
    if family == 'glibc':
        assert '__libc_start_main' in markers
    if family == 'legacy_gnu_seed':
        assert '__libc_start_main' not in markers and ('_impure_ptr' in markers or '__getreent' in markers)
    return {'runtime_family': family, 'symbol_markers': markers, 'sha256': expected, 'bytes': path.stat().st_size}

programs = []
with tempfile.TemporaryDirectory(prefix='xos_retained_elf_', dir=args.scratch) as folder:
    root = Path(folder)
    for m in members:
        if m['type'] == 3:
            continue
        binary = root / 'boot.elf'
        begin, end = m['data_off'], m['data_off'] + m['data_len']
        binary.write_bytes(bundle[begin:end])
        programs.append({'delivery': 'installer', 'path': '/usr/bin/' + m['name'],
                         **static_receipt(binary, m['sha256'].hex(), 'glibc')})
        binary.unlink()
    with Disk(disk_path, root, read_only=True) as disk:
        for label, group in pkgs.items():
            for item in group['executables']:
                binary = disk.export(item['path'])
                programs.append({'delivery': label, 'path': item['path'],
                                 **static_receipt(binary, item['sha256'], 'glibc')})
                binary.unlink()
        for name in (*TOOLS, MAKE_PATH):
            binary = disk.export(name)
            family = 'glibc' if name == MAKE_PATH else 'legacy_gnu_seed'
            programs.append({'delivery': 'gnu_seed', 'path': name,
                             **static_receipt(binary, seed['installed_files'][name], family)})
            binary.unlink()
        assert all(not disk.info(path) for path in ('/usr/bin/dash', '/usr/bin/xypm'))
assert artifact(disk_path) == release['work_disk']
ordinary_system_path = args.system / 'manifest.json'
ordinary_system, _ = metadata_snapshot(ordinary_system_path, release['system']['manifest_sha256'])
ordinary_programs = {}
for name, item in ordinary_system['artifacts'].items():
    if not name.endswith('.image.elf'):
        continue
    path = args.system / name
    assert sha_file(path) == item['sha256']
    result = subprocess.run([nm, '--defined-only', path], capture_output=True, text=True)
    assert result.returncode == (1 if name == 'user_bad_magic.image.elf' else 0)
    assert not re.search(r'\s__libc_start_main$', result.stdout, flags=re.MULTILINE)
    ordinary_programs[name] = {'symbol_table_read': result.returncode == 0, 'sha256': item['sha256']}
counts = dict(Counter(p['runtime_family'] for p in programs))
missing = sorted(p['path'] for p in programs if p['runtime_family'] == 'glibc' and p['sha256'] != boot_apps['xypm'])
print(json.dumps({
    'candidate_commit': release['candidate_source_commit'], 'status': 'inventory_verified',
    'release_manifest_sha256': release_sha, 'distribution_manifest_sha256': dist_sha,
    'asset_count': len(expected_assets), 'package_profile_sha256': profile_sha,
    'work_disk_sha256': release['work_disk']['sha256'], 'gnu_seed_receipt_sha256': seed_sha,
    'gnu_seed_sources_sha256': release['archives']['gnu-seed-sources.tar.gz']['sha256'],
    'gnu_make_signer': seed_material['make']['source_verified_signer'],
    'gnu_seed_source_files': len(seed_material['files']), 'gnu_seed_notice_files': len(seed_material['notices']),
    'gnu_seed_nested_source_archives': nested_gnu_archives, 'gcc_source_matches_sdk_lock': gcc_source,
    'gnu_seed_frozen_source_build_sha256': seed_material['frozen']['build_manifest_sha256'],
    'components_manifest_sha256': components_sha, 'component_source_files': len(components['records']),
    'packages': pkgs, 'installer_bundle_sha256': installer['boot_bundle']['container_sha256'],
    'python_source_signature_receipt_sha256': sha_file(args.python_signature_receipt),
    'ordinary_system_symbols': ordinary_programs,
    'program_counts': counts, 'programs': programs, 'xypm_relink_manifest_sha256': dist['xypm_relink_manifest_sha256'],
    'relinkable_programs': [boot_apps['xypm']],
    'remaining_glibc_relink_paths': missing, 'glibc_local_source_verified_against_lock': args.glibc_source is not None,
    'glibc_source_lock': {name: source_lock[name] for name in (
        'archive', 'archive_bytes', 'archive_sha256', 'signature_sha256', 'upstream_url')},
    'glibc_sdk_verification_status': signed_report['status'],
    'glibc_sdk_license_files': sorted(sdk_license_names), 'glibc_sdk_raw_source_member_present': False,
}, sort_keys=True, indent=2))
