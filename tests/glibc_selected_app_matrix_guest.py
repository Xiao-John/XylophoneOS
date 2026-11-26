# SPDX-License-Identifier: Apache-2.0
"""Run the selected glibc applications and GNU Make from one installed XOS disk."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_candidate import inspect_app_kit
from cpython_py0b_smoke import run
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes
from work_disk import transfer
from xypm_format import MAX_MANIFEST, load_json, require, sha_file, strict_json, verify_package
from xypm_image import query_image


def verify_build_receipt(package, profile, binding, expected_id, *, app_receipt):
    verified = verify_package(package, profile)
    manifest = verified['manifest']
    receipt = manifest['build_receipt']
    data = bytearray()

    def capture(event, item, content):
        if item['path'] == receipt['path'] and event == 'begin':
            require(item['size'] <= MAX_MANIFEST, 'build receipt exceeds the supported size')
        if item['path'] == receipt['path'] and event == 'data':
            data.extend(content)

    verify_package(package, profile, expected_sha256=verified['sha256'], sink=capture)
    record = strict_json(bytes(data))
    require(manifest['id'] == expected_id and record['runtime_family'] == 'glibc'
            and (not app_receipt or (record['project_id'] == expected_id
                                     and record['target_profile'] == binding['profile_id']))
            and all(record[key] == binding[key] for key in
                    ('sdk_manifest_sha256', 'sdk_tree_sha256', 'profile_sha256')),
            'XPK build receipt differs from the selected application SDK')
    return {'id': manifest['id'], 'xpk_sha256': verified['sha256'],
            'build_receipt_sha256': receipt['sha256']}


def stock_installer(candidate_dir, candidate, installed, profile, binding):
    bundle = installed.get('boot_bundle')
    if bundle is None:
        return None
    members = {(item['type'], item['name']): item['sha256'] for item in bundle['members']}
    require(bundle['format'] == 'XOSBND1' and bundle['container_sha256'] == installed['dash_sha256']
            and bundle['container_bytes'] == installed['dash_bytes']
            and len(bundle['members']) == 3
            and members.keys() == {(1, 'dash'), (3, 'daily'), (5, 'xypm')},
            'unexpected stock installer bundle contents')
    artifacts = candidate['artifacts']
    for name in ('stock/daily.xpk', 'stock/xypm.elf', 'dash_manifest.json', 'system/xos-install.iso'):
        require(sha_file(candidate_dir / name) == artifacts[name],
                'stock candidate artifact differs from its manifest: ' + name)
    dash = load_json(candidate_dir / 'dash_manifest.json')
    require(members[(1, 'dash')] == dash['sha256']
            and dash['inputs']['profile'] == binding['profile_sha256']
            and dash['inputs']['sdk/manifest.json'] == binding['sdk_manifest_sha256']
            and members[(3, 'daily')] == artifacts['stock/daily.xpk']
            and members[(5, 'xypm')] == artifacts['stock/xypm.elf'],
            'stock bundle differs from the installer inputs')
    daily = verify_build_receipt(candidate_dir / 'stock/daily.xpk', profile, binding,
                                 'xos.daily_utilities', app_receipt=False)
    return {'bundle_sha256': bundle['container_sha256'], 'dash_sha256': members[(1, 'dash')],
            'xypm_sha256': members[(5, 'xypm')], 'reboot_iso_sha256': artifacts['system/xos-install.iso'],
            'daily': daily}


def check_packages(disk, profile, packages):
    records = query_image(disk, profile)['packages']
    expected = {entry['id']: entry['xpk_sha256'] for entry in packages}
    require(len(records) == len(expected) == len(packages)
            and {entry['id']: entry['sha256'] for entry in records} == expected,
            'installed package identities or digests differ from the matrix inputs')
    return {**query_image(disk, profile, 'verify-installed'), 'packages': records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate', 'sdk-kit', 'c-xpk', 'cxx-xpk', 'make-manifest', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--stock-install-timeout', type=int, default=600,
                        help='seconds to allow automatic stock installation before reporting failure')
    parser.add_argument('--require-command-substitution', action='store_true',
                        help='verify dash command substitution in both stock guest boots')
    args = parser.parse_args()
    if args.stock_install_timeout < 1:
        parser.error('--stock-install-timeout must be positive')
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = args.candidate / 'candidate_manifest.json'
    candidate = load_json(receipt)
    binding = candidate['application_sdk']
    profile = args.sdk_kit / 'profile.json'
    profile_data = load_json(profile)
    image = args.candidate / 'system/xos-install-dash.iso'
    install_receipt = args.candidate / 'system/install_manifest.json'
    installed = load_json(install_receipt)
    make = load_json(args.make_manifest)
    make_elf = args.make_manifest.parent / make['elf']['path']
    require(candidate['installer_guest_qualification'] == 'passed'
            and sha_file(image) == candidate['artifacts']['system/xos-install-dash.iso']
            and sha_file(install_receipt) == candidate['artifacts']['system/install_manifest.json']
            and installed['build_id'] == candidate['build_id'], 'installer receipt does not bind the ISO')
    require(sha_file(profile) == binding['profile_file_sha256'] == make['profile_sha256']
            and sha_file(args.sdk_kit / 'sdk/manifest.json') == binding['sdk_manifest_sha256'] == make['sdk_manifest_sha256']
            and sha_file(make_elf) == make['elf']['sha256'], 'Make and the installer must use the same SDK')
    stock = stock_installer(args.candidate, candidate, installed, profile_data, binding)
    if args.require_command_substitution and stock is None:
        parser.error('--require-command-substitution needs an installed stock bundle')
    if stock:
        make_lock = load_json(ROOT / 'src/ports/gnu_make/source_lock.json')
        require(inspect_app_kit(args.sdk_kit) == binding
                and make['sdk_tree_sha256'] == binding['sdk_tree_sha256']
                and make['status'] == 'built_not_run'
                and make['source_verified_signer'] == make_lock['signer_primary_fingerprint']
                and make['archive_sha256'] == make_lock['sha256']
                and make['signature_sha256'] == make_lock['signature_sha256'],
                'GNU Make must be built from verified source with the selected stock SDK')

    report = {'status': 'failed', 'candidate_source': candidate['source_commit'],
               'build_id': candidate['build_id'], 'candidate_manifest_sha256': sha_file(receipt),
               'iso_sha256': sha_file(image), 'sdk_manifest_sha256': binding['sdk_manifest_sha256'],
               'sdk_tree_sha256': binding['sdk_tree_sha256'], 'profile_id': binding['profile_id'],
               'profile_sha256': sha_file(profile), 'make_sha256': sha_file(make_elf),
               'make_manifest_sha256': sha_file(args.make_manifest),
               'packages': {},
               'runner_sha256': sha_file(Path(__file__)), 'boots': [],
               'command_substitution_required': args.require_command_substitution}
    if stock:
        report['stock'] = stock
        report['make_source'] = {key: make[key] for key in
                                 ('archive_sha256', 'signature_sha256', 'upstream_keyring_sha256',
                                  'source_verified_signer')}
    try:
        with tempfile.TemporaryDirectory(prefix='xos_cold_matrix_') as lab:
            work = Path(lab)
            disk = work / 'initial.img'
            create_fat32(disk, 512)
            for label, source, expected_id in [('c', args.c_xpk, 'selection.kit_c'),
                                               ('cxx', args.cxx_xpk, 'selection.kit_cpp')]:
                package = work / f'{label}.xpk'
                shutil.copyfile(source, package)
                report['packages'][label] = verify_build_receipt(package, profile_data, binding,
                                                                 expected_id, app_receipt=True)
                next_disk = work / f'{label}.img'
                subprocess.run([sys.executable, str(ROOT / 'scripts/xypm.py'), 'install', str(package),
                                '--offline', '--profile', str(profile), '--image', str(disk),
                                '--output-image', str(next_disk)], check=True, stdout=subprocess.DEVNULL)
                disk = next_disk
            if stock:
                external = list(report['packages'].values())
                report['offline_external_install'] = check_packages(disk, profile_data, external)
                combined_packages = [*external, stock['daily']]
            transfer(disk, 'mkdir', '/state')
            fixtures = {'user.txt': 'glibc-user-data\n',
                        'apps.sh': 'set -e\nkit_c\n/usr/bin/kit_cpp\n'
                                   'gmake -r -B -f /state/Makefile all\necho XOS_COLD_APP_MATRIX_OK\n',
                        'Makefile': '.PHONY: all\nall:\n\t@/usr/bin/kit_c\n'
                                    "\t@printf '%s\\n' 'XOS_MAKE_RECIPE_OK';\n"}
            if stock:
                fixtures['apps.sh'] += (
                    'if [ "$1" = install ]; then\n'
                    '  /usr/bin/cp /state/user.txt /state/retained.txt\n'
                    'fi\n'
                    'test -f /state/retained.txt\n'
                    '/usr/bin/cat /state/retained.txt\n'
                    'echo XOS_STOCK_DAILY_OK\n'
                )
            if args.require_command_substitution:
                fixtures['apps.sh'] += (
                    'value=$(/usr/bin/cat /state/retained.txt)\n'
                    'test "$value" = glibc-user-data\n'
                    'echo XOS_STOCK_SUBSTITUTION_OK\n'
                )
            for name, content in fixtures.items():
                path = work / name
                path.write_text(content)
                transfer(disk, 'import', '/state/' + name, path)
            transfer(disk, 'import', '/usr/bin/gmake', make_elf)
            for index in range(2):
                label = f'cold_matrix_{index + 1}'
                boot_image = args.candidate / 'system/xos-install.iso' if stock and index else image
                image_expected = stock['reboot_iso_sha256'] if stock and index else report['iso_sha256']
                require(sha_file(boot_image) == image_expected, 'selected boot ISO changed before launch')
                guest = Guest(boot_image, label, work_disk=disk, log_dir=args.output)
                try:
                    report['qemu'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
                    guest.expect(b'xos64> ', timeout=45)
                    offset = len(guest.output)
                    send_bytes(guest, b'run\r')
                    if index == 0:
                        if stock:
                            guest.expect(b'[files] bundle installed: /usr/bin/dash', start=offset,
                                         timeout=args.stock_install_timeout)
                            guest.expect(b'[files] bundle packages installed', start=offset,
                                         timeout=args.stock_install_timeout)
                            require(b'xypm-recover: committed transaction cleaned' in guest.output[offset:],
                                    'stock installation did not clean the committed transaction')
                        else:
                            guest.expect(b'[files] dash installed', start=offset, timeout=90)
                    guest.expect_supervisor(trace=True, start=offset, timeout=60)
                    before = resources(guest)
                    start = len(guest.output)
                    command_line = 'dash /state/apps.sh'
                    if stock:
                        command_line += ' reboot' if index else ' install'
                    output = run(guest, command_line, timeout=180)
                    milestones = ('GLIBC_KIT_C_OK 2.44', 'GLIBC_KIT_CPP_OK vector thread exception',
                                  'XOS_MAKE_RECIPE_OK', 'XOS_COLD_APP_MATRIX_OK', 'kind=exited code=0')
                    if stock:
                        milestones += ('XOS_STOCK_DAILY_OK',)
                        require('glibc-user-data' in output.splitlines(),
                                f'daily cat did not read the retained data in {label}')
                    if args.require_command_substitution:
                        milestones += ('XOS_STOCK_SUBSTITUTION_OK',)
                    require(all(marker in output for marker in milestones)
                            and output.count(milestones[0]) == 2, f'Unexpected application outcome in {label}')
                    after = resources(guest)
                    transition = bytes(guest.output[start:])
                    retired = {int(pid) for pid in re.findall(rb'event=killed_by_supervisor pid=(\d+)', transition)}
                    reclaimed = {int(pid): int(pages) for pid, pages in
                                 re.findall(rb'event=reclaimed pid=(\d+) pages=(\d+)', transition)}
                    require(retired in (set(), {1, 2, 3, 4}) and retired <= reclaimed.keys(),
                            'unexpected task retirement during the initial installation launch')
                    require(after == (before[0] + sum(reclaimed[pid] for pid in retired),
                                      before[1] - len(retired), before[2]), 'dash did not restore its resources')
                    require('GNU Make 4.4.1' in run(guest, 'gmake --version', timeout=45)
                            and resources(guest) == after, 'GNU Make did not return to the resource baseline')
                    command(guest, 'sync', b'[files] sync=ok', timeout=45)
                    require(sha_file(boot_image) == image_expected, 'selected boot ISO changed during the test')
                    boot_record = {'outcome': 'passed', 'image_sha256': image_expected,
                                   'before': before, 'after': after,
                                   'retired_demo_tasks': sorted(retired), 'markers': milestones}
                finally:
                    guest.close()
                    serial = args.output / (label + '.serial.log')
                    serial.write_bytes(guest.output)
                    report.setdefault('serial_sha256', {})[label] = sha_file(serial)
                if stock:
                    boot_record['installed_packages'] = check_packages(disk, profile_data, combined_packages)
                    if index == 0:
                        boot_record['automatic_install'] = 'completed_and_cleaned'
                report['boots'].append(boot_record)
            expected_files = {'/usr/bin/dash': stock['dash_sha256'] if stock else installed['dash_sha256'],
                              '/usr/bin/gmake': make['elf']['sha256'],
                              '/state/user.txt': sha_file(work / 'user.txt')}
            if stock:
                expected_files['/state/retained.txt'] = expected_files['/state/user.txt']
            report['preserved_files'] = {}
            for path, expected in expected_files.items():
                readback = work / 'readback'
                transfer(disk, 'export', path, readback)
                require(sha_file(readback) == expected, f'changed file on final work disk: {path}')
                report['preserved_files'][path] = expected
                readback.unlink()
            report['status'] = 'passed_subset'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'])


if __name__ == '__main__':
    main()
