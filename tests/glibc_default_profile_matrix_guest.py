# SPDX-License-Identifier: Apache-2.0
"""Start each frozen package profile, reject foreign XPKs, and verify retained disks."""
import argparse
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_candidate import inspect_app_kit
from glibc_selected_app_matrix_guest import verify_build_receipt
from make_work_disk import create_fat32
from package_g4_cross_version_guest import boot, command, MARKERS
from package_p2_faults import sparse_copy
from process_smoke import resources
from shell_launch_support import bind_system
from xypm_format import canonical, load_json, PackageError, require, sha_file, verify_package
from xypm_image import Disk, query_image, transact

ROLES = ('unified', 'stock', 'browser')
USER_FILE = '/out/user.txt'


def inspect_case(item):
    kit = Path(item['kit'])
    profile_path = kit / 'profile.json'
    profile = load_json(profile_path)
    binding = inspect_app_kit(kit)
    package = Path(item['package'])
    package_info = verify_package(package, profile)
    package_id = package_info['manifest']['id']
    verified = verify_build_receipt(package, profile, binding, package_id,
                                    app_receipt=package_id != 'xos.daily_utilities')
    manager = load_json(item['xypm_receipt'])
    elf = Path(manager['elf'])
    receipt = load_json(elf.parent / 'build_receipt.json')
    require(receipt['project_id'] == 'xos.xypm' and receipt['target_profile'] == profile['id']
            and sha_file(elf) == receipt['output_sha256'], 'xypm ELF and build receipt differ')
    require(all(receipt[key] == binding[key] for key in
                ('profile_sha256', 'sdk_manifest_sha256', 'sdk_tree_sha256')),
            'xypm build receipt differs from its SDK')
    return {'elf': elf, 'package': package, 'profile': profile, 'package_id': package_id,
            'description': verified | {'profile': dict(binding), 'xypm_elf_sha256': sha_file(elf)}}


def readback(disk_path, scratch, case):
    profile = case['profile']
    packages = query_image(disk_path, profile)['packages']
    require(len(packages) == 1 and packages[0]['id'] == case['package_id']
            and packages[0]['sha256'] == case['description']['xpk_sha256'], 'original package was changed')
    with tempfile.TemporaryDirectory(dir=scratch) as folder, Disk(disk_path, folder, True) as disk:
        require(all(disk.info(marker) is None for marker in MARKERS), 'unexpected xypm transaction material')
        hashes = {name: sha_file(disk.export(name)) for name in
                  (USER_FILE, '/var/lib/xypm/db.json', '/var/lib/xypm/index.tsv', '/out/xypm')}
    return {'packages': packages, 'file_sha256': hashes,
            'verified_files': query_image(disk_path, profile, 'verify-installed')['files']}


def check_host_rejection(case, foreign):
    try:
        verify_package(foreign['package'], case['profile'])
    except PackageError as error:
        require('package target profile mismatch' in str(error), str(error))
        return
    raise AssertionError('host silently accepted a foreign package')


def run_case(image, output, role, cases):
    case = cases[role]
    foreign = {label: item for label, item in cases.items() if label != role}
    for item in foreign.values():
        check_host_rejection(case, item)

    note = output / 'user.txt'
    marker = f'user data on retained {role} profile'
    note.write_text(marker + '\n')
    source = output / 'source.img'
    create_fat32(source, 512)
    with Disk(source, output) as disk:
        disk.command('mkdir', '/out')
        disk.command('import', USER_FILE, note)
        disk.command('import', '/out/xypm', case['elf'])
        for label, item in foreign.items():
            disk.command('import', f'/out/{label}.xpk', item['package'])
    original = output / 'original.img'
    transact(source, original, case['profile'], 'install', package=case['package'])
    expected = readback(original, output, case)
    require(expected['file_sha256'][USER_FILE] == sha_file(note), 'user-data setup differs')

    def read_in_guest(guest):
        command(guest, 'exec-file /out/xypm --version', b'xypm 0.4.0 (P3 offline repositories)')
        command(guest, 'exec-file /out/xypm list', case['package_id'].encode())
        command(guest, 'cat ' + USER_FILE, marker.encode())

    control = output / 'control.img'
    sparse_copy(original, control)
    with boot(image, control, 'control', output) as guest:
        read_in_guest(guest)
        command(guest, 'sync', b'[files] sync=ok')
    trial = output / 'rejected.img'
    sparse_copy(original, trial)
    with boot(image, trial, 'rejected', output) as guest:
        read_in_guest(guest)
        baseline = resources(guest)
        for name in foreign:
            denied = command(guest, f'maint-run /out/xypm install /out/{name}.xpk', b'maintenance: retained')
            require(b'package target profile differs from this xypm build' in denied, 'wrong refusal reason')
            recovery = command(guest, 'maint-recover-boot', b'maintenance: completed')
            require(b'xypm-recover: no transaction' in recovery, 'foreign package left a transaction')
            require(resources(guest) == baseline, 'resource drift after rejection')
        read_in_guest(guest)
        command(guest, 'sync', b'[files] sync=ok')
    require(readback(trial, output, case) == readback(control, output, case) == expected,
            'refusal changed the database, owned files, package indexes, manager, or user data')
    digest = sha_file(trial)
    require(digest == sha_file(control), 'refusal wrote additional disk bytes')
    cold_disks = {}
    for label, disk in (('control', control), ('rejected', trial)):
        stage = label + '_cold'
        cold = output / (stage + '.img')
        sparse_copy(disk, cold)
        with boot(image, cold, stage, output) as guest:
            read_in_guest(guest)
            command(guest, 'sync', b'[files] sync=ok')
        cold_disks[label] = (cold, sha_file(cold))
    require(cold_disks['control'][1] == cold_disks['rejected'][1]
            and readback(cold_disks['rejected'][0], output, case) == expected,
            'cold recovery retained a disk difference')
    return case['description'] | {
        'accepted_readback': expected, 'rejected_profiles': {k: v['profile']['id'] for k, v in foreign.items()},
        'source_disk_sha256': sha_file(original), 'boot_only_and_refusal_disk_sha256': digest,
        'cold_boot_control_and_refusal_disk_sha256': cold_disks['rejected'][1],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'inputs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'cases': {}, 'test_sha256': sha_file(__file__)}
    try:
        inputs = load_json(args.inputs)
        require(set(inputs) == set(ROLES), 'expected unified, former stock, and ClarkE profiles')
        cases = {role: inspect_case(inputs[role]) for role in ROLES}
        require(len({case['profile']['id'] for case in cases.values()}) == len(cases), 'profiles are not distinct')
        image = args.system.resolve() / 'xos-install.iso'
        info = bind_system(args.system.resolve())
        report['system_build_id'] = info['build_id']
        report['image_sha256'] = sha_file(image)
        report['system_manifest_sha256'] = sha_file(args.system / 'manifest.json')
        for role in ROLES:
            folder = output / role
            folder.mkdir()
            report['cases'][role] = run_case(image, folder, role, cases)
        report['status'] = 'passed'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (output / 'report.json').write_bytes(canonical(report))


if __name__ == '__main__':
    main()
