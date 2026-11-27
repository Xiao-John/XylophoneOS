# SPDX-License-Identifier: Apache-2.0
"""Archive source correspondence for the non-Seed ports in a glibc release."""

import argparse
from gzip import GzipFile
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile

from package_application_preview import artifact
from package_glibc_release import KIT, MANIFEST, inspect_candidate, inspect_packages, verify_archive_members
from xypm_format import canonical, load_json, require, sha_file

ROOT = Path(__file__).resolve().parents[1]
FORMAT = 'xos_glibc_release_component_sources_v1'
PYTHON = 'src/ports/cpython/'
SBASE = 'src/ports/sbase/'
PACKAGE_IDS = {'daily': 'xos.daily_utilities', 'cpython': 'xos.cpython', 'wheel': 'python_idna'}
NAMES = ('Python-3.14.9.tar.xz', 'zlib-1.3.2.tar.xz', 'idna-3.20-py3-none-any.whl', 'sbase.tar.gz')


def git(*args):
    return subprocess.check_output(['git', '-C', ROOT, *args])


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def put(target, data):
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(data)


def git_object(kind, data):
    return hashlib.sha1(f'{kind} {len(data)}\0'.encode() + data, usedforsecurity=False).digest()


def verify_sbase(path, lock):
    # Compare the original Git tree, including file modes. A tar header's
    # commit comment alone does not authenticate the archived file contents.
    nodes, locked_files = {}, {}
    with tarfile.open(path, 'r:gz') as archive:
        for item in archive:
            parts = PurePosixPath(item.name).parts
            require(parts and parts[0] == 'sbase' and '..' not in parts
                    and PurePosixPath(item.name).as_posix() == item.name, 'unexpected sbase archive path')
            if item.isdir():
                continue
            require(len(parts) > 1 and item.isfile(), 'sbase archive requires ordinary source files')
            folder = nodes
            for part in parts[1:-1]:
                folder = folder.setdefault(part, {})
                require(isinstance(folder, dict), 'sbase file used as a directory')
            require(parts[-1] not in folder, 'duplicate sbase archive path')
            with archive.extractfile(item) as file:
                data = file.read()
            folder[parts[-1]] = (b'100755' if item.mode & 0o111 else b'100644', git_object('blob', data))
            name = '/'.join(parts[1:])
            if name in lock['files']:
                locked_files[name] = hashlib.sha256(data).hexdigest()

    def tree(node):
        entries = []
        for name in sorted(node, key=lambda name: name.encode() + (b'/' if isinstance(node[name], dict) else b'')):
            child = node[name]
            mode, digest = (b'40000', tree(child)) if isinstance(child, dict) else child
            entries.append(mode + b' ' + name.encode() + b'\0' + digest)
        return git_object('tree', b''.join(entries))

    require(locked_files == lock['files'] and tree(nodes).hex() == lock['tree'], 'sbase tree differs from source lock')


def source_inputs(dash, daily, cli, zlib):
    inputs = {
        name: digest for name, digest in dash['inputs'].items() if name.startswith(('src/', 'scripts/'))
    }
    inputs.update({SBASE + item['source']: item['source_sha256'] for item in daily['tools']})
    inputs[SBASE + 'daily_utilities.json'] = daily['registry_sha256']
    inputs['scripts/build_daily_utilities.py'] = daily['builder_sha256']
    inputs['scripts/stage_glibc_daily_runtime.py'] = daily['debug_stage']['builder_sha256']
    python_inputs = {PYTHON + name: digest for name, digest in cli['port_inputs'].items()}
    python_inputs.update({'scripts/' + name: digest for name, digest in cli['builder_inputs'].items()})
    python_inputs['scripts/build_cpython_zlib.py'] = zlib['inputs']['build_script_sha256']
    return inputs, python_inputs


def collect_files(args, root):
    release = load_json(args.release / MANIFEST)
    profile_path = args.release / KIT / 'profile.json'
    profile = load_json(profile_path)
    paths, candidate = inspect_candidate(args.candidate, args.release / KIT)
    require(all(release[name] == value for name, value in candidate.items()), 'release differs from candidate')
    packages = args.release / 'packages'
    verified = inspect_packages(profile, candidate, packages / 'daily.xpk',
                                packages / 'cpython.xpk', packages / 'wheel.xpk')
    receipts = root / 'receipts'
    for name, (path, package) in verified.items():
        require(package['sha256'] == release['packages'][name]['sha256'], 'release XPK differs: ' + name)
        with tarfile.open(path, 'r:') as archive:
            for member, target in (
                ('manifest.json', name + '_package.json'),
                ('payload/usr/share/' + PACKAGE_IDS[name] + '/build_receipt.json', name + '_build.json'),
            ):
                put(receipts / target, archive.extractfile(member).read())
    for source, name in (
        (args.release / MANIFEST, 'release.json'),
        (profile_path, 'profile.json'),
        (args.candidate / 'candidate_manifest.json', 'candidate.json'),
        (paths['dash_manifest.json'], 'dash.json'),
        (paths['system/install_manifest.json'], 'installer.json'),
        (paths['installer_guest_report.json'], 'installer_guest.json'),
        (args.cpython_receipt, 'cpython_cli.json'),
        (args.zlib_receipt, 'zlib.json'),
    ):
        copy(source, receipts / name)
    require(sha_file(args.release / 'images/xos-install-dash.iso') == release['installer_iso']['sha256'],
            'published installer bytes differ')

    daily, dash, cli, zlib = (load_json(receipts / name)
                             for name in ('daily_build.json', 'dash.json', 'cpython_cli.json', 'zlib.json'))
    release_inputs, python_inputs = source_inputs(dash, daily, cli, zlib)
    python_inputs['scripts/package_cpython_glibc.py'] = load_json(receipts / 'cpython_build.json')['packager_sha256']
    release_inputs.update({name: None for name in (
        'src/ports/sbase/source_lock.json', 'src/ports/sbase/upstream/LICENSE', 'src/ports/sbase/README.md',
        'scripts/build_glibc_daily_bundle.py', 'scripts/package_daily_utilities.py', 'scripts/xypm_python_wheel.py',
        'scripts/build_glibc_program.py', 'scripts/build_install_iso.py', 'LICENSE', 'NOTICE')})
    for prefix, revision, inputs in (
        ('candidate', release['candidate_source_commit'], release_inputs),
        ('python', args.cpython_commit, python_inputs),
    ):
        require(git('rev-parse', revision + '^{commit}').decode().strip() == revision, 'require exact source commit')
        for name, expected in inputs.items():
            data = git('show', revision + ':' + name)
            require(expected is None or hashlib.sha256(data).hexdigest() == expected,
                    'XOS source differs from build receipt: ' + name)
            put(root / 'xos' / prefix / name, data)
    for source, name in zip((args.cpython_archive, args.zlib_archive, args.idna_wheel, args.sbase_archive), NAMES, strict=True):
        copy(source, root / 'archives' / name)
    return {'release_manifest_sha256': sha_file(receipts / 'release.json'), 'cpython_commit': args.cpython_commit}


def check_bindings(root, binding):
    receipts = root / 'receipts'
    release, candidate, installer, guest, dash, daily, cp, cli, zlib, idna = (
        load_json(receipts / (name + '.json')) for name in (
            'release', 'candidate', 'installer', 'installer_guest', 'dash', 'daily_build',
            'cpython_build', 'cpython_cli', 'zlib', 'wheel_build'))
    require(sha_file(receipts / 'release.json') == binding['release_manifest_sha256']
            and sha_file(receipts / 'candidate.json') == release['candidate_manifest_sha256']
            and sha_file(receipts / 'profile.json') == release['application_sdk']['profile_file_sha256']
            and sha_file(receipts / 'installer.json') == release['installer_manifest_sha256']
            and sha_file(receipts / 'installer_guest.json') == release['installer_guest_sha256']
            and sha_file(receipts / 'dash.json') == candidate['artifacts']['dash_manifest.json'],
            'release receipt binding differs')
    members = {(item['type'], item['name']): item['sha256'] for item in installer['boot_bundle']['members']}
    require(guest['status'] == 'passed' and guest['iso_sha256'] == release['installer_iso']['sha256']
            and guest['iso_files']['DASH.ELF'] == installer['boot_bundle']['container_sha256']
            and members[(1, 'dash')] == dash['sha256'] == release['dash_sha256'],
            'installer does not bind the selected Dash executable')
    require(sha_file(receipts / 'cpython_cli.json') == cp['cli_build_receipt_sha256']
            and cli['executable']['sha256'] == cp['interpreter']['debug_sha256']
            and sha_file(receipts / 'zlib.json') == cp['zlib']['build_receipt_sha256']
            and zlib['libz_sha256'] == cp['zlib']['artifacts']['lib/libz.a'], 'interpreter or zlib build binding differs')
    payloads = {}
    for name, package in release['packages'].items():
        p = load_json(receipts / (name + '_package.json'))
        require(p['id'] == PACKAGE_IDS[name] and len(p['files']) == package['files']
                and sha_file(receipts / (name + '_build.json')) == p['build_receipt']['sha256'],
                'package receipt differs: ' + name)
        payloads[name] = {entry['path']: entry['sha256'] for entry in p['files']}
    require(payloads['cpython']['usr/bin/python3'] == cp['interpreter']['sha256']
            and all(payloads['daily'][tool['guest_path'].lstrip('/')] == tool['elf_sha256']
                    for tool in daily['tools']), 'packaged executable binding differs')
    release_inputs, python_inputs = source_inputs(dash, daily, cli, zlib)
    python_inputs['scripts/package_cpython_glibc.py'] = cp['packager_sha256']
    for directory, inputs in (('candidate', release_inputs), ('python', python_inputs)):
        for name, digest in inputs.items():
            require(sha_file(root / 'xos' / directory / name) == digest, 'archived XOS input differs: ' + name)
    port = root / 'xos/python' / PYTHON
    for name, expected in zip(NAMES[:3], (cp['source_archive_sha256'], cp['zlib']['source_archive_sha256'],
                                        idna['wheel_sha256']), strict=True):
        require(sha_file(root / 'archives' / name) == expected, 'upstream archive differs: ' + name)
    require(load_json(port / 'source_lock.json')['sha256'] == cp['source_archive_sha256']
            and load_json(port / 'zlib_lock.json')['sha256'] == zlib['inputs']['archive_sha256']
            == cp['zlib']['source_archive_sha256']
            and load_json(port / 'idna_lock.json')['wheel_sha256'] == idna['wheel_sha256'],
            'upstream archive differs from source lock')
    sbase_lock = load_json(root / 'xos/candidate' / SBASE / 'source_lock.json')
    require(sbase_lock['commit'] == daily['source_commit'], 'sbase commit differs')
    verify_sbase(root / 'archives' / NAMES[3], sbase_lock)


def build(args):
    args.output.parent.mkdir(parents=True, exist_ok=True)
    require(not args.output.exists() and not args.output.is_symlink(), 'choose a new materials output')
    with tempfile.TemporaryDirectory(dir=args.output.parent) as folder:
        work = Path(folder)
        root = work / 'inputs'
        binding = collect_files(args, root)
        check_bindings(root, binding)
        records = {p.relative_to(root).as_posix(): artifact(p) for p in sorted(root.rglob('*')) if p.is_file()}
        stage = work / 'materials'
        stage.mkdir()
        archive = stage / 'component-sources.tar.gz'
        with archive.open('xb') as output, GzipFile(filename='', mode='wb', fileobj=output, mtime=0) as packed, \
                tarfile.open(fileobj=packed, mode='w|', format=tarfile.USTAR_FORMAT) as tar:
            for name, record in records.items():
                item = tarfile.TarInfo(name)
                item.size = record['bytes']
                with (root / name).open('rb') as source:
                    tar.addfile(item, source)
        verify_archive_members(archive, records)
        put(stage / 'component-sources.json',
            canonical({'format': FORMAT, 'archive': artifact(archive), 'binding': binding, 'records': records}))
        stage.rename(args.output)


def verify(args):
    require(sha_file(args.manifest) == args.manifest_sha256, 'materials manifest digest differs')
    receipt = load_json(args.manifest)
    require(receipt['format'] == FORMAT and artifact(args.archive) == receipt['archive'], 'materials archive differs')
    verify_archive_members(args.archive, receipt['records'])
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        with tarfile.open(args.archive, 'r:gz') as archive:
            for item in archive:
                require(item.name in receipt['records'] and item.isfile(), 'unexpected received file')
                target = root / item.name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(item) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output)
        require({p.relative_to(root).as_posix(): artifact(p) for p in root.rglob('*') if p.is_file()} == receipt['records'],
                'received data differs from manifest')
        check_bindings(root, receipt['binding'])
    print(canonical({'status': 'passed', 'files': len(receipt['records']), **receipt['binding']}).decode(), end='')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for name, action, paths, values in (
        ('build', build, ('release', 'candidate', 'cpython-receipt', 'zlib-receipt', 'cpython-archive',
                          'zlib-archive', 'idna-wheel', 'sbase-archive', 'output'), ('cpython-commit',)),
        ('verify', verify, ('archive', 'manifest'), ('manifest-sha256',)),
    ):
        step = sub.add_parser(name)
        step.set_defaults(run=action)
        for flag in paths:
            step.add_argument('--' + flag, type=Path, required=True)
        for flag in values:
            step.add_argument('--' + flag, required=True)
    args = parser.parse_args()
    args.run(args)


if __name__ == '__main__':
    main()
