# SPDX-License-Identifier: Apache-2.0
"""Stage the native GNU Seed and its corresponding source as release assets."""
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile

from build_gnu_make import PORT, verify_source
from check_frozen_gnu_seed_sources import CORRESPONDENCE, SEED_RECORD, verify as verify_frozen_sources
from package_application_preview import artifact
from package_glibc_release import KIT, verify_archive_members
from prepare_glibc_gnu_seed import (DRIVER_DIR, FROZEN, MAKE_PATH, SYSROOT, TOOLS, common_receipt,
                                   driver_specs, stage_disk, sysroot_files, verify_installed)
from xypm_format import MAX_MANIFEST, canonical, load_json, require, sha_file, strict_json
from xypm_sdk_profile import metadata_snapshot, relative_file

ROOT = Path(__file__).resolve().parents[1]
SEED_RECEIPT = 'gnu_seed_receipt.json'
SOURCE_ARCHIVE = 'gnu-seed-sources.tar.gz'
MATERIALS_DIR = 'gnu-seed-sources'
MATERIALS_MANIFEST = 'manifest.json'
REQUIRED_NOTICES = {'GNU GCC Seed and compiler host C++ runtime', 'GNU Binutils Seed',
                    'GMP', 'MPFR', 'MPC', 'newlib', 'GNU Make for XOS'}


def copy_material(source, root, name, expected):
    name = PurePosixPath(name)
    require(not name.is_absolute() and '..' not in name.parts, 'invalid materials path')
    dest = root / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as stream, dest.open('xb') as output:
        shutil.copyfileobj(stream, output, 1 << 20)
    require(sha_file(dest) == expected, 'GNU Seed material differs: ' + str(name))
    return dest


def notice_files():
    components = load_json(ROOT / 'licenses/components.json')['components']
    selected = {entry['name']: entry for entry in components if entry['name'] in REQUIRED_NOTICES}
    require(set(selected) == REQUIRED_NOTICES, 'GNU Seed notice inventory is incomplete')
    notices = {}
    for component in selected.values():
        for name in component['notices']:
            notices[name] = component['artifact_sha256'][name]
    zlib = 'src/ports/binutils/upstream/zlib-LICENSE'
    expected = next(entry['artifact_sha256'][zlib] for entry in components if zlib in entry.get('notices', ()))
    notices[zlib] = expected
    return notices


def make_materials(materials, make_receipt, source_dir, installed, work):
    lock = load_json(PORT / 'source_lock.json')
    record = load_json(make_receipt)
    archive_name = 'make-' + lock['version'] + '.tar.gz'
    source = relative_file(source_dir, archive_name)
    signature = relative_file(source_dir, archive_name + '.sig')
    keyring = relative_file(source_dir, 'gnu-keyring.gpg')
    require(sha_file(keyring) == record['upstream_keyring_sha256'], 'GNU Make signer keyring differs from build')
    verify_source(lock, source, signature, keyring, work / 'make_signature.log')
    require(record['elf']['sha256'] == installed[MAKE_PATH], 'GNU Make source receipt differs from staged ELF')
    names = {
        archive_name: (source, lock['sha256']),
        archive_name + '.sig': (signature, lock['signature_sha256']),
        'gnu-keyring.gpg': (keyring, record['upstream_keyring_sha256']),
    }
    for name, (path, expected) in names.items():
        copy_material(path, materials, 'make/' + name, expected)
    inputs = {'scripts/build_gnu_make.py',
              *(path.relative_to(ROOT).as_posix() for path in PORT.rglob('*') if path.is_file())}
    require(inputs == record['inputs'].keys(), 'GNU Make build recipe or patch inventory differs')
    for name, expected in record['inputs'].items():
        copy_material(relative_file(ROOT, name), materials, 'make/port/' + name, expected)
    copy_license = 'src/ports/gnu_make/upstream/COPYING'
    require(record['inputs'][copy_license] == installed['/usr/share/licenses/gnu_make/COPYING'],
            'installed GNU Make license differs from the source receipt')
    return {key: record[key] for key in ('version', 'target', 'archive_sha256', 'signature_sha256',
                                        'source_verified_signer', 'upstream_keyring_sha256',
                                        'sdk_manifest_sha256', 'sdk_tree_sha256', 'profile_sha256',
                                        'config_sha256', 'inputs')} | {'elf_sha256': installed[MAKE_PATH]}


def assemble(output, disk, kit, profile, release, seed, archive):
    donor_dir, make_receipt, make_source_dir = seed
    with tempfile.TemporaryDirectory(prefix='.gnu_seed_', dir=output) as directory:
        work = Path(directory)
        materials = work / MATERIALS_DIR
        materials.mkdir()
        frozen_root = materials / 'frozen'
        frozen = verify_frozen_sources(donor_dir, material_root=frozen_root)
        hashes = stage_disk(disk, kit, profile, release['application_sdk'], donor_dir, make_receipt, work)
        require(all(hashes[name] == digest for name, digest in frozen['tools'].items()),
                'installed compiler tools differ from frozen source correspondence')
        make = make_materials(materials, make_receipt, make_source_dir, hashes, work)
        notices = notice_files()
        for name, expected in notices.items():
            copy_material(ROOT / name, materials, 'notices/' + name, expected)
        receipt = {'status': 'assembled_release_seed', **common_receipt(release, make_receipt),
                   'installed_files': hashes, 'work_disk_sha256': sha_file(disk)}
        inventory = {path.relative_to(materials).as_posix(): artifact(path)
                     for path in sorted(materials.rglob('*')) if path.is_file()}
        manifest = {'schema': 1, 'frozen': frozen, 'make': make, 'notices': notices, 'files': inventory}
        material_manifest = materials / MATERIALS_MANIFEST
        material_manifest.write_bytes(canonical(manifest))
        archive(materials, output / SOURCE_ARCHIVE)
        path = disk.parent / SEED_RECEIPT
        path.write_bytes(canonical(receipt))
        return {'receipt': artifact(path), 'sources_manifest': artifact(material_manifest)}


def check_archive(archive_path, binding):
    name = MATERIALS_DIR + '/' + MATERIALS_MANIFEST
    with tarfile.open(archive_path, 'r:gz') as archive:
        entry = archive.getmember(name)
        require(entry.isfile() and entry.size == binding['bytes'] <= MAX_MANIFEST,
                'invalid GNU Seed source manifest entry')
        body = archive.extractfile(entry).read()
    require(hashlib.sha256(body).hexdigest() == binding['sha256'], 'GNU Seed source manifest differs')
    manifest = strict_json(body)
    require(manifest['schema'] == 1, 'invalid GNU Seed source manifest schema')
    files = {MATERIALS_DIR + '/' + name: digest for name, digest in manifest['files'].items()}
    files[name] = binding
    verify_archive_members(archive_path, files)
    return manifest


def verify_materials(manifest, hashes, sdk):
    inventory = manifest['files']
    frozen = manifest['frozen']
    anchor = {item['name']: item['sha256'] for item in load_json(FROZEN)['assets']}
    require(frozen['source_asset_sha256'] == anchor['xos-0.0.2-1103-sources.tar.gz']
            and frozen['release_manifest_sha256'] == anchor['release_manifest.json']
            and set(frozen['artifacts']) == set(CORRESPONDENCE)
            and inventory['frozen/' + SEED_RECORD]['sha256'] == frozen['build_manifest_sha256'],
            'GNU Seed frozen correspondence differs')
    for name, record in frozen['artifacts'].items():
        require(inventory['frozen/' + name] == {'sha256': record['sha256'], 'bytes': record['bytes']},
                'GNU Seed frozen material differs: ' + name)

    notices = notice_files()
    require(manifest['notices'] == notices and all(
        inventory['notices/' + name]['sha256'] == digest for name, digest in notices.items()),
        'GNU Seed license material is incomplete')
    make = manifest['make']
    lock = load_json(PORT / 'source_lock.json')
    source = 'make/make-' + lock['version'] + '.tar.gz'
    make_inputs = {'scripts/build_gnu_make.py',
                   *(path.relative_to(ROOT).as_posix() for path in PORT.rglob('*') if path.is_file())}
    require(make['version'] == lock['version'] and make['target'] == lock['target']
            and make['source_verified_signer'] == lock['signer_primary_fingerprint']
            and make['archive_sha256'] == inventory[source]['sha256'] == lock['sha256']
            and make['signature_sha256'] == inventory[source + '.sig']['sha256'] == lock['signature_sha256']
            and inventory['make/gnu-keyring.gpg']['sha256'] == make['upstream_keyring_sha256']
            and set(make['inputs']) == make_inputs
            and all(inventory['make/port/' + name]['sha256'] == digest for name, digest in make['inputs'].items())
            and hashes['/usr/share/licenses/gnu_make/COPYING'] == notices['src/ports/gnu_make/upstream/COPYING'],
            'GNU Make source or port recipe is incomplete')
    expected_files = {'frozen/' + name for name in (SEED_RECORD, *CORRESPONDENCE)}
    expected_files.update('notices/' + name for name in notices)
    expected_files.update('make/port/' + name for name in make_inputs)
    expected_files.update((source, source + '.sig', 'make/gnu-keyring.gpg'))
    require(set(inventory) == expected_files, 'GNU Seed source archive has unexpected material')
    require(set(frozen['tools']) == set(TOOLS)
            and all(hashes[name] == digest for name, digest in frozen['tools'].items())
            and make['elf_sha256'] == hashes[MAKE_PATH]
            and make['sdk_manifest_sha256'] == sdk['sdk_manifest_sha256']
            and make['sdk_tree_sha256'] == sdk['sdk_tree_sha256']
            and make['profile_sha256'] == sdk['profile_file_sha256'],
            'GNU Seed source materials belong to different tools or SDK')


def verify(release, profile, archive_root, disk):
    binding = release['gnu_seed']
    path = relative_file(disk.parent, SEED_RECEIPT)
    require(path.stat().st_size == binding['receipt']['bytes'], 'GNU Seed receipt size differs')
    receipt, _ = metadata_snapshot(path, binding['receipt']['sha256'])
    require(receipt['status'] == 'assembled_release_seed' and receipt['system'] == release['system']
            and receipt['sdk'] == release['application_sdk'] and receipt['packages'] == release['packages']
            and receipt['candidate_source_commit'] == release['candidate_source_commit']
            and receipt['installer_iso'] == release['installer_iso'] and receipt['dash_sha256'] == release['dash_sha256']
            and receipt['xypm_sha256'] == release['xypm_sha256']
            and receipt['work_disk_sha256'] == release['work_disk']['sha256'], 'GNU Seed belongs to another release')
    manifest = check_archive(relative_file(archive_root, SOURCE_ARCHIVE), binding['sources_manifest'])
    hashes = receipt['installed_files']
    verify_materials(manifest, hashes, receipt['sdk'])
    expected_sysroot = {name: sha_file(path) for name, path in sysroot_files(archive_root / KIT, profile).items()}
    actual_sysroot = {name: digest for name, digest in hashes.items() if name.startswith(SYSROOT + '/')}
    require(expected_sysroot == actual_sysroot
            and hashes[DRIVER_DIR + '/specs'] == hashlib.sha256(driver_specs(profile).encode()).hexdigest(),
            'GNU Seed disk is bound to a different glibc sysroot')
    with tempfile.TemporaryDirectory(prefix='xos_release_seed_check_') as directory:
        verify_installed(disk, hashes, Path(directory))
    return receipt
