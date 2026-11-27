# SPDX-License-Identifier: Apache-2.0
"""Assemble a qualified glibc installer and its same-profile release work disk."""
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile

from build_candidate import inspect_app_kit
from make_work_disk import create_fat32
from package_application_preview import artifact, inspect_system
from package_cpython_glibc import LANDMARK, LIBRARY, PROGRAM
from xypm_format import MAX_MANIFEST, canonical, load_json, require, sha_file, strict_json, verify_package
from xypm_image import Disk, query_image, transact
from xypm_sdk_profile import metadata_snapshot, relative_file

ROOT = Path(__file__).resolve().parents[1]
IMAGES = 'images'
KIT = 'application-sdk'
MANIFEST = 'release_manifest.json'
ORDINARY = 'xos-install.iso'
INSTALLER = 'xos-install-dash.iso'


def candidate_file(root, name, artifacts):
    path = relative_file(root, name)
    require(sha_file(path) == artifacts[name], 'candidate artifact differs: ' + name)
    return path


def inspect_candidate(root, kit):
    candidate, digest = metadata_snapshot(relative_file(root, 'candidate_manifest.json'))
    binding = inspect_app_kit(kit)
    require(candidate['application_sdk'] == binding, 'candidate belongs to a different glibc SDK/profile')
    require(candidate['installer_guest_qualification'] == 'passed', 'candidate lacks installer guest qualification')
    artifacts = candidate['artifacts']
    names = ('system/manifest.json', 'system/install_manifest.json', 'system/' + ORDINARY,
             'system/' + INSTALLER, 'dash_manifest.json', 'stock/build_receipt.json',
             'stock/daily.xpk', 'stock/xypm.elf', 'installer_guest_report.json', 'stock_guest/report.json')
    paths = {name: candidate_file(root, name, artifacts) for name in names}
    ordinary = inspect_system(paths['system/' + ORDINARY], paths['system/manifest.json'])
    system = load_json(paths['system/manifest.json'])
    installer = load_json(paths['system/install_manifest.json'])
    dash = load_json(paths['dash_manifest.json'])
    bundle = installer['boot_bundle']
    members = {(item['type'], item['name']): item['sha256'] for item in bundle['members']}
    kernel = system['artifacts']['kernel.bin']['sha256']
    require(candidate['build_id'] == ordinary['build_id'] == installer['build_id']
            and installer['kernel_sha256'] == kernel and bundle['format'] == 'XOSBND1'
            and bundle['container_sha256'] == installer['dash_sha256']
            and len(bundle['members']) == 3
            and members == {(1, 'dash'): dash['sha256'], (3, 'daily'): artifacts['stock/daily.xpk'],
                            (5, 'xypm'): artifacts['stock/xypm.elf']}, 'candidate installer bundle differs')
    require(dash['profile'] == 'dash_glibc_preview' and dash['inputs']['profile'] == binding['profile_sha256']
            and dash['inputs']['sdk/manifest.json'] == binding['sdk_manifest_sha256'],
            'installer dash is bound to another SDK/profile')
    tested = load_json(paths['installer_guest_report.json'])
    stock = load_json(paths['stock_guest/report.json'])
    require(tested['status'] == stock['status'] == 'passed'
            and tested['build_id'] == stock['system_build_id'] == ordinary['build_id']
            and tested['iso_sha256'] == stock['installer_iso_sha256'] == artifacts['system/' + INSTALLER]
            and tested['iso_files']['KERNEL.BIN'] == kernel
            and tested['iso_files']['DASH.ELF'] == bundle['container_sha256']
            and stock['image_sha256'] == ordinary['iso']['sha256']
            and stock['xypm_elf_sha256'] == artifacts['stock/xypm.elf']
            and stock['xypm_receipt_sha256'] == artifacts['stock/build_receipt.json']
            and stock['dash_receipt_sha256'] == artifacts['dash_manifest.json']
            and stock['profile_binding_sha256'] == binding['profile_sha256']
            and stock['sdk_manifest_sha256'] == binding['sdk_manifest_sha256']
            and stock['package_sha256'] == artifacts['stock/daily.xpk'],
            'installer or stock guest qualification does not bind the candidate')
    return paths, {'candidate_manifest_sha256': digest, 'candidate_source_commit': candidate['source_commit'],
                   'system': ordinary, 'application_sdk': binding,
                   'installer_guest_sha256': artifacts['installer_guest_report.json'],
                   'stock_guest_sha256': artifacts['stock_guest/report.json'],
                   'installer_manifest_sha256': artifacts['system/install_manifest.json'],
                   'installer_iso': artifact(paths['system/' + INSTALLER]),
                   'dash_sha256': dash['sha256'], 'xypm_sha256': artifacts['stock/xypm.elf'],
                   'daily_sha256': artifacts['stock/daily.xpk']}


def receipt(package, profile, expected_id):
    contents = bytearray()

    def capture(event, entry, data):
        if event == 'data' and entry['path'] == f'usr/share/{expected_id}/build_receipt.json':
            require(len(contents) + len(data) <= MAX_MANIFEST, 'package build receipt is too large')
            contents.extend(data)

    verified = verify_package(package, profile, sink=capture)
    manifest = verified['manifest']
    require(manifest['id'] == expected_id and manifest['build_receipt']['path'] ==
            f'usr/share/{expected_id}/build_receipt.json', 'unexpected release package identity or receipt')
    return verified, strict_json(bytes(contents))


def inspect_packages(profile, proof, daily, python, wheel):
    binding = proof['application_sdk']
    daily_pkg, daily_build = receipt(daily, profile, 'xos.daily_utilities')
    python_pkg, python_build = receipt(python, profile, 'xos.cpython')
    require(daily_pkg['sha256'] == proof['daily_sha256'], 'daily XPK differs from the qualified installer')
    require(daily_build['runtime_family'] == 'glibc' and all(daily_build[key] == binding[key] for key in
            ('sdk_tree_sha256', 'sdk_manifest_sha256', 'profile_sha256')), 'daily receipt is bound to another SDK')
    require(python_build['runtime_family'] == 'glibc' and python_build['sdk_manifest_sha256'] == binding['sdk_manifest_sha256']
            and python_build['profile_file_sha256'] == binding['profile_file_sha256']
            and python_build['sdk_binding']['sdk_tree_sha256'] == binding['sdk_tree_sha256'],
            'CPython receipt is bound to another SDK')
    python_files = {item['path']: item['sha256'] for item in python_pkg['manifest']['files']}
    python_lock = load_json(ROOT / 'src/ports/cpython/source_lock.json')
    zlib = load_json(ROOT / 'src/ports/cpython/zlib_lock.json')
    with_zlib = python_build.get('zlib', {})
    require(python_pkg['manifest']['upstream_version'] == python_lock['version']
            and python_build['source_archive_sha256'] == python_lock['sha256']
            and all(with_zlib.get(key) == zlib[lock_key] for key, lock_key in
                (('version', 'version'), ('source_archive_sha256', 'sha256'), ('license_sha256', 'license_sha256')))
            and python_files['usr/share/licenses/xos.cpython/zlib/LICENSE'] == zlib['license_sha256']
            and python_files[PROGRAM] == python_build['interpreter']['sha256']
            and python_files[LIBRARY] == python_build['library']['sha256']
            and python_files[LANDMARK] == python_build['library']['members']['os.py'],
            'release requires the verified CPython zlib XPK')
    packages = {'daily': (daily, daily_pkg), 'cpython': (python, python_pkg)}
    if wheel:
        idna_pkg, idna = receipt(wheel, profile, 'python_idna')
        lock = load_json(ROOT / 'src/ports/cpython/idna_lock.json')
        files = {item['path']: item['sha256'] for item in idna_pkg['manifest']['files']}
        require(idna_pkg['manifest']['upstream_version'] == lock['version']
                and idna['wheel_sha256'] == lock['wheel_sha256'] and idna['license_sha256'] == lock['license_sha256']
                and files['usr/share/licenses/python_idna/LICENSE.md'] == lock['license_sha256']
                and all(entry['role'] == 'data' for entry in idna_pkg['manifest']['files']),
                'release requires the locked pure Python IDNA wheel')
        packages['wheel'] = (wheel, idna_pkg)
    claimed = {'usr/bin/dash', 'usr/bin/xypm'}
    for _, package in packages.values():
        for item in package['manifest']['files']:
            path = item['path'].casefold()
            require(path not in claimed, 'release package path collision: ' + item['path'])
            claimed.add(path)
    return packages


def copy_bound(source, destination, digest):
    shutil.copyfile(source, destination)
    require(sha_file(destination) == digest, 'release input changed: ' + source.name)


def assemble(output, candidate, kit, daily, cpython, wheel, archive, *, seed=None):
    paths, proof = inspect_candidate(candidate, kit)
    profile, _ = metadata_snapshot(relative_file(kit, 'profile.json'), proof['application_sdk']['profile_file_sha256'])
    packages = inspect_packages(profile, proof, daily, cpython, wheel)
    output.mkdir(parents=True, exist_ok=False)
    try:
        images = output / IMAGES
        images.mkdir()
        (output / 'packages').mkdir()
        disk = images / 'work_disk.img'
        create_fat32(disk, 512)
        with Disk(disk, output) as fat:
            for name in ('/bin', '/src', '/out', '/tmp'):
                fat.command('mkdir', name)
        records = {}
        with tempfile.TemporaryDirectory(prefix='.transactions_', dir=output) as work:
            for name, (source, checked) in packages.items():
                saved = output / 'packages' / (name + '.xpk')
                copy_bound(source, saved, checked['sha256'])
                next_disk = Path(work) / (name + '.img')
                transaction = transact(disk, next_disk, profile, 'install', package=saved,
                                       expected_sha256=checked['sha256'])
                next_disk.replace(disk)
                (output / (name + '_install_receipt.json')).write_bytes(canonical(transaction))
                records[name] = {'id': checked['manifest']['id'], 'sha256': checked['sha256'],
                                 'files': len(checked['manifest']['files'])}
        verify_disk(disk, profile, records)
        for name, destination, digest in (
            (ORDINARY, images / ORDINARY, proof['system']['iso']['sha256']),
            (INSTALLER, images / INSTALLER, proof['installer_iso']['sha256']),
            ('manifest.json', output / 'system_manifest.json', proof['system']['manifest_sha256']),
            ('install_manifest.json', images / 'install_manifest.json', proof['installer_manifest_sha256']),
        ):
            copy_bound(paths['system/' + name], destination, digest)
        shutil.copyfile(ROOT / 'scripts/release_launcher.py', images / 'launch.py')
        shutil.copytree(kit, output / KIT, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.cache'))
        require(inspect_app_kit(output / KIT) == proof['application_sdk'], 'release application SDK changed')
        release = {'schema_version': 1, 'status': 'assembled_glibc_candidate', **proof,
                   'work_disk': artifact(disk), 'packages': records,
                   'launcher_sha256': sha_file(images / 'launch.py')}
        archives = ['images.tar.gz', 'application-sdk.tar.gz']
        if seed is not None:
            from package_glibc_gnu_seed import SOURCE_ARCHIVE, assemble as assemble_seed
            release['gnu_seed'] = assemble_seed(output, disk, output / KIT, profile, release, seed, archive)
            release['work_disk'] = artifact(disk)
            verify_disk(disk, profile, records)
            archive(output / 'packages', output / 'packages.tar.gz')
            archives.extend((SOURCE_ARCHIVE, 'packages.tar.gz'))
        (images / 'release.json').write_bytes(canonical(release))
        archive(images, output / 'images.tar.gz')
        archive(output / KIT, output / 'application-sdk.tar.gz')
        release['archives'] = {name: artifact(output / name) for name in archives}
        (output / MANIFEST).write_bytes(canonical(release))
        if seed is not None:
            (output / 'CHECKSUMS.sha256').write_bytes(release_checksums(output, release))
        return release
    except BaseException:
        shutil.rmtree(output)
        raise


def release_checksums(root, release):
    assets = {name: item['sha256'] for name, item in release['archives'].items()}
    assets[MANIFEST] = sha_file(root / MANIFEST)
    assets['system_manifest.json'] = release['system']['manifest_sha256']
    return ''.join(f'{digest}  {name}\n' for name, digest in sorted(assets.items())).encode()


def verify_archive_members(archive_path, expected, *, directories=()):
    paths = {name: PurePosixPath(name) for name in (*expected, *directories)}
    require(all(path.parts and not path.is_absolute() and '..' not in path.parts
                and path.as_posix() == name for name, path in paths.items()),
            'release archive member path is invalid')
    parents = {parent.as_posix() for path in paths.values() for parent in path.parents if parent.parts}
    parents.update(directories)
    pending = dict(expected)
    seen = set()
    with tarfile.open(archive_path, 'r|gz') as archive:
        for entry in archive:
            require(entry.name not in seen, 'duplicate release archive member: ' + entry.name)
            seen.add(entry.name)
            if entry.isdir() and entry.name in parents:
                continue
            require(entry.isfile() and entry.name in pending, 'unexpected release archive member: ' + entry.name)
            record = pending.pop(entry.name)
            require(entry.size == record['bytes'], 'release archive entry size differs: ' + entry.name)
            with archive.extractfile(entry) as stream:
                require(hashlib.file_digest(stream, 'sha256').hexdigest() == record['sha256'],
                        'release archive entry differs: ' + entry.name)
    require(not pending and set(directories) <= seen, 'release archive inventory is incomplete')


def verify_disk(disk, profile, packages):
    expected = {record['id']: record['sha256'] for record in packages.values()}
    installed = query_image(disk, profile, 'list')['packages']
    require({record['id']: record['sha256'] for record in installed} == expected,
            'release disk package ownership differs from package inputs')
    result = query_image(disk, profile, 'verify-installed')
    require(result['files'] == sum(record['files'] for record in packages.values()),
            'release disk file inventory differs from packages')
    return result


def verify_assembled(root):
    release, _ = metadata_snapshot(relative_file(root, MANIFEST))
    require(release['schema_version'] == 1 and release['status'] == 'assembled_glibc_candidate',
            'expected an assembled glibc release candidate')
    require(inspect_app_kit(root / KIT) == release['application_sdk'], 'release SDK differs from receipt')
    profile, _ = metadata_snapshot(relative_file(root, KIT + '/profile.json'),
                                   release['application_sdk']['profile_file_sha256'])
    ordinary = inspect_system(relative_file(root, IMAGES + '/' + ORDINARY),
                              relative_file(root, 'system_manifest.json'))
    require(ordinary == release['system'], 'release ordinary system differs from receipt')
    for name, expected in {
        IMAGES + '/' + INSTALLER: release['installer_iso']['sha256'],
        IMAGES + '/install_manifest.json': release['installer_manifest_sha256'],
        IMAGES + '/launch.py': release['launcher_sha256'],
        IMAGES + '/work_disk.img': release['work_disk']['sha256'],
        **{name: receipt['sha256'] for name, receipt in release['archives'].items()},
    }.items():
        require(sha_file(relative_file(root, name)) == expected, 'release artifact differs: ' + name)
    for name, record in release['packages'].items():
        require(sha_file(relative_file(root, 'packages/' + name + '.xpk')) == record['sha256'],
                'release package differs: ' + name)
    inside = load_json(relative_file(root, IMAGES + '/release.json'))
    require(inside == {name: value for name, value in release.items() if name != 'archives'},
            'embedded image release receipt differs')
    disk = relative_file(root, IMAGES + '/work_disk.img')
    verify_disk(disk, profile, release['packages'])
    if 'gnu_seed' in release:
        from package_glibc_gnu_seed import SOURCE_ARCHIVE, verify as verify_seed
        required_archives = {name + '.tar.gz' for name in (IMAGES, KIT, 'packages')}
        require(set(release['archives']) == {SOURCE_ARCHIVE, *required_archives},
                'GNU Seed release archive inventory differs')
        require(relative_file(root, 'CHECKSUMS.sha256').read_bytes() == release_checksums(root, release),
                'GNU Seed release checksums differ')
        verify_seed(release, profile, root, disk)
        for name in (IMAGES, KIT, 'packages'):
            tree = root / name
            files = {path.relative_to(root).as_posix(): artifact(path)
                     for path in tree.rglob('*') if path.is_file()}
            directories = {path.relative_to(root).as_posix() for path in (tree, *tree.rglob('*'))
                           if path.is_dir()}
            verify_archive_members(relative_file(root, name + '.tar.gz'), files, directories=directories)
    return release, profile
