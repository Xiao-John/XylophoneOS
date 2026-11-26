# SPDX-License-Identifier: Apache-2.0
"""Qualify native XPK install, disk stdlib, reboot and removal of glibc CPython."""

import argparse
import gzip
from io import BytesIO
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from glibc_selected_app_matrix_guest import check_packages, stock_installer
from glibc_static_guest import system_sources
from iso_dash_install import iso_files
from make_work_disk import create_fat32
from package_cpython_glibc import LANDMARK, LIBRARY, PACKAGE, PROGRAM, RECEIPT
from package_p2_faults import boot_maintenance_guest, resources, sparse_copy
from package_p2_verify_guest import quiet_maintenance_guest
from task_smoke import send_bytes
from xypm_format import DEFAULT_PROFILE, canonical, load_json, require, sha_file, strict_json, verify_package
from xypm_image import DB_PATH, INDEX_PATH, Disk
from xypm_sdk_profile import metadata_snapshot, verify_profile


def package_receipt(package, profile):
    captured = bytearray()

    def capture(event, item, data):
        if event == 'data' and item['path'] == RECEIPT:
            captured.extend(data)

    checked = verify_package(package, profile, sink=capture)
    manifest = checked['manifest']
    require(manifest['id'] == PACKAGE and manifest['build_receipt']['path'] == RECEIPT,
            'unexpected CPython package identity')
    files = {item['path']: item for item in manifest['files']}
    receipt = strict_json(captured)
    require(files[PROGRAM]['sha256'] == receipt['interpreter']['sha256']
            and files[LIBRARY]['sha256'] == receipt['library']['sha256']
            and files[LANDMARK]['sha256'] == receipt['library']['members']['os.py'],
            'CPython executable or disk library differs from package receipt')
    return checked, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system-build', 'sdk', 'profile', 'package', 'cpython-build', 'xypm-build', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--stock-candidate', type=Path, help='boot the same-profile stock installer on the work disk')
    parser.add_argument('--previous-profile', type=Path)
    parser.add_argument('--previous-package', type=Path, help='a different-profile build of the same CPython XPK')
    parser.add_argument('--maintenance-timeout', type=int, default=600)
    args = parser.parse_args()
    if args.maintenance_timeout <= 0:
        parser.error('maintenance timeout must be positive')
    if bool(args.previous_profile) != bool(args.previous_package):
        parser.error('--previous-profile and --previous-package are required together')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sys_path = args.system_build / 'manifest.json'
    sysmeta = load_json(sys_path)
    image = args.system_build / 'xos-install.iso'
    profile, profile_digest = metadata_snapshot(args.profile)
    binding = verify_profile(profile, 'glibc', args.sdk)
    sdk_digest = profile['sdk_binding']['sdk_manifest_sha256']
    xypm = load_json(args.xypm_build)
    manager = Path(xypm['elf'])
    manager_receipt_path = manager.parent / 'build_receipt.json'
    manager_receipt = load_json(manager_receipt_path)
    cli_build = args.cpython_build / 'py0a_report.json'
    package, receipt = package_receipt(args.package, profile)
    zlib = receipt.get('zlib')

    def verify_inputs():
        require(system_sources() == sysmeta['sources']
                and sha_file(image) == sysmeta['artifacts']['xos-install.iso']['sha256'],
                'ordinary system or sources differ')
        require(manager_receipt['runtime_family'] == 'glibc'
                and xypm['target_profile'] == manager_receipt['target_profile'] == profile['id']
                and manager_receipt['sdk_manifest_sha256'] == sdk_digest
                and manager_receipt['profile_sha256'] == binding['profile_sha256']
                and manager_receipt['output_sha256'] == sha_file(manager),
                'native xypm differs from the CPython package profile')
        require(receipt['sdk_binding'] == binding and receipt['sdk_manifest_sha256'] == sdk_digest
                and receipt['profile_file_sha256'] == profile_digest
                and receipt['cli_build_receipt_sha256'] == sha_file(cli_build)
                and sha_file(args.package) == package['sha256']
                and sha_file(args.profile) == profile_digest
                and verify_profile(profile, 'glibc', args.sdk) == binding,
                'CPython package inputs differ')
        require(zlib == load_json(cli_build).get('zlib'), 'CPython zlib package and CLI build differ')

    verify_inputs()
    report = {'status': 'failed', 'system_build_id': sysmeta['build_id'],
              'image_sha256': sha_file(image), 'system_manifest_sha256': sha_file(sys_path),
              'sdk_manifest_sha256': sdk_digest, 'profile_sha256': profile_digest,
              'package_sha256': package['sha256'], 'xypm_elf_sha256': sha_file(manager),
              'xypm_receipt_sha256': sha_file(manager_receipt_path),
              'cli_build_receipt_sha256': sha_file(cli_build), 'interpreter': receipt['interpreter'],
              'library_sha256': receipt['library']['sha256'], 'test_sha256': sha_file(Path(__file__)),
              'stdlib_members': len(receipt['library']['members']), 'checks': []}
    if zlib:
        report['zlib'] = zlib
    guest = None
    try:
        def reject(other_package, other_profile):
            try:
                verify_package(other_package, other_profile)
            except ValueError as error:
                require('target profile mismatch' in str(error), 'unexpected cross-profile rejection')
            else:
                raise ValueError('foreign profile admitted the CPython package')

        reject(args.package, load_json(DEFAULT_PROFILE))
        report['checks'].append('frozen_newlib_profile_rejected')
        if args.previous_package:
            previous = load_json(args.previous_profile)
            old, _ = package_receipt(args.previous_package, previous)
            reject(args.previous_package, profile)
            reject(args.package, previous)
            report['previous_package'] = {'sha256': old['sha256'], 'profile': previous['id'],
                                          'profile_sha256': sha_file(args.previous_profile)}
            report['checks'].append('host_cross_profile_rejections')

        expected_packages = []
        stock = None
        if args.stock_candidate:
            candidate = args.stock_candidate.resolve()
            require(args.system_build.resolve() == candidate / 'system', 'stock and ordinary system roots differ')
            candidate_receipt = candidate / 'candidate_manifest.json'
            stock_build = load_json(candidate_receipt)
            install_receipt = candidate / 'system/install_manifest.json'
            install = load_json(install_receipt)
            installer = candidate / 'system/xos-install-dash.iso'
            artifacts = stock_build['artifacts']
            require(stock_build['build_id'] == install['build_id'] == sysmeta['build_id']
                    and sha_file(installer) == artifacts['system/xos-install-dash.iso']
                    and sha_file(install_receipt) == artifacts['system/install_manifest.json'],
                    'stock installer does not match the candidate')
            application_sdk = stock_build['application_sdk']
            require(application_sdk['profile_file_sha256'] == profile_digest
                    and application_sdk['profile_sha256'] == binding['profile_sha256']
                    and application_sdk['sdk_manifest_sha256'] == sdk_digest
                    and application_sdk['sdk_tree_sha256'] == binding['sdk_tree_sha256'],
                    'stock installer and CPython package use distinct SDKs')
            stock = stock_installer(candidate, stock_build, install, profile, application_sdk)
            require(stock and stock['xypm_sha256'] == report['xypm_elf_sha256'], 'stock xypm differs from test input')
            iso = iso_files(installer)
            require(iso['KERNEL.BIN'] == sysmeta['artifacts']['kernel.bin']['sha256']
                    and iso['DASH.ELF'] == stock['bundle_sha256'], 'stock ISO differs from build receipts')
            expected_packages.append(stock['daily'])
            report['stock'] = {**stock, 'installer_iso_sha256': sha_file(installer),
                               'candidate_manifest_sha256': sha_file(candidate_receipt),
                               'source_commit': stock_build['source_commit']}
        with tempfile.TemporaryDirectory(prefix='cpython_glibc_p2_') as folder:
            work = Path(folder)
            disk = (output if stock else work) / 'work.img'
            create_fat32(disk, 512)
            user_file = work / 'user.txt'
            user_file.write_text('pre-existing user data\n')
            fixtures = ROOT / 'tests/fixtures'
            files = {
                '/out/cpython.xpk': args.package,
                '/work/user.txt': user_file,
                '/tests/stdlib.py': fixtures / 'cpython_glibc/installed_stdlib.py',
                '/tests/startup.py': fixtures / 'cpython_glibc/startup_probe.py',
                '/tests/py1.py': fixtures / 'cpython_py1/stdlib_probe.py',
                '/tests/a1.py': fixtures / 'cpython_py3_a1/stdlib_probe.py',
                '/tests/missing.py': fixtures / 'cpython_py1/missing_import.py',
            }
            if not stock:
                files['/usr/bin/xypm'] = manager
            if args.previous_package:
                files['/out/old-python.xpk'] = args.previous_package
            if zlib:
                files['/tests/zlib.py'] = fixtures / 'cpython_py3_a2/zlib_probe.py'
            with Disk(disk, work) as fat:
                for path in ('/usr', '/usr/bin', '/out', '/work', '/work/py3a1', '/tests'):
                    fat.command('mkdir', path)
                if zlib:
                    fat.command('mkdir', '/work/py3a2')
                for path, source in files.items():
                    fat.command('import', path, source)

            def command(line, success, timeout):
                start = len(guest.output)
                send_bytes(guest, line.encode() + b'\r')
                failures = (b'maintenance: retained', b'maintenance: busy or denied')
                result = guest.expect_any((success, *(failure for failure in failures if failure != success)),
                                          start=start, timeout=timeout)
                require(result == success, 'maintenance failed: ' + line)
                guest.expect_supervisor(start=start, timeout=40)
                return bytes(guest.output[start:])

            if stock:
                guest = Guest(installer, 'cpython_stock_install', work_disk=disk, iso=True, log_dir=output)
                guest.expect(b'xos64> ', timeout=40)
                send_bytes(guest, b'run\r')
                guest.expect(b'[files] bundle packages installed', timeout=args.maintenance_timeout)
                guest.expect_supervisor(trace=True, timeout=40)
                require(b'xypm-recover: committed transaction cleaned' in guest.output, 'stock setup lacks cleanup')
                quiet_maintenance_guest(guest)
                report['stock']['resources'] = resources(guest)
                guest.close()
                guest = None
                with Disk(disk, work, True) as fat:
                    require(sha_file(fat.export('/usr/bin/xypm')) == stock['xypm_sha256']
                            and sha_file(fat.export('/usr/bin/dash')) == stock['dash_sha256'],
                            'stock disk has unexpected dash or xypm')
                report['stock']['installed_files'] = check_packages(disk, profile, expected_packages)['files']
                sparse_copy(disk, output / 'stock-installed.img')
                report['stock']['disk_sha256'] = sha_file(disk)
                report['checks'].append('stock_installer_and_disk_receipts')

            if args.previous_package:
                def rejection_state():
                    with Disk(disk, work, True) as fat:
                        paths = tuple(path for path in (DB_PATH, INDEX_PATH, '/work/user.txt') if fat.info(path))
                        require(fat.info('/' + PROGRAM) is None and
                                all(fat.info('/var/lib/xypm/' + name) is None
                                    for name in ('transaction', 'txdata', 'transaction_commit')),
                                'CPython or transaction files appeared during rejection')
                        return {path: sha_file(fat.export(path)) for path in paths}

                original = rejection_state()
                guest = boot_maintenance_guest(image, 'cpython_previous_profile', disk)
                baseline = resources(guest)
                data = command('maint-run /usr/bin/xypm install /out/old-python.xpk',
                               b'maintenance: retained', args.maintenance_timeout)
                require(b'package target profile differs from this xypm build' in data, 'wrong native rejection')
                data = command('maint-recover-boot', b'maintenance: completed', 60)
                require(b'xypm-recover: no transaction' in data and resources(guest) == baseline,
                        'cross-profile rejection left a transaction or leaked resources')
                guest.close()
                (output / 'previous_profile.log').write_bytes(guest.output)
                guest = None
                require(rejection_state() == original, 'wrong-profile rejection changed ownership or user data')
                check_packages(disk, profile, expected_packages)
                report['previous_package']['unchanged_files'] = original
                report['previous_package']['resources'] = baseline
                report['checks'].append('native_previous_profile_install_rejected')

            guest = boot_maintenance_guest(image, 'cpython_p2_install', disk)
            report['qemu'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            baseline = resources(guest)
            report['install_baseline'] = baseline
            command('xypm install /out/cpython.xpk', b'maintenance write lease required', 60)
            require(resources(guest) == baseline, 'resource drift after denied install')
            report['checks'].append('ordinary_install_denied')
            data = command('maint-run /usr/bin/xypm install /out/cpython.xpk --sha256 ' + package['sha256'],
                           b'maintenance: completed', args.maintenance_timeout)
            require(b'committed transaction cleaned' in data and resources(guest) == baseline,
                    'install cleanup or resource recovery failed')
            report['checks'].append('native_p2_install')
            guest.close()
            (output / 'install.log').write_bytes(guest.output)
            guest = None
            managed = package['manifest']['files']
            active_packages = [*expected_packages, {'id': PACKAGE, 'xpk_sha256': package['sha256']}]
            installed = check_packages(disk, profile, active_packages)['files']
            stock_files = report.get('stock', {}).get('installed_files', 0)
            report['installed_files'] = installed - stock_files
            require(report['installed_files'] == len(managed), 'installed files differ')
            if stock:
                sparse_copy(disk, output / 'cpython-installed.img')
                report['installed_disk_sha256'] = sha_file(disk)

            guest = boot_maintenance_guest(image, 'cpython_p2_exec_remove', disk)
            baseline = resources(guest)
            report['run_baseline'] = baseline
            data = command('exec-file /usr/bin/python3 -B /tests/stdlib.py', b'kind=exited code=', 180)
            require(re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', data) == [b'0'],
                    'installed CPython did not exit successfully')
            for marker in (b'CPYTHON_XPK_DISK_STDLIB', b'CPYTHON_G4_CLOCK_PASS', b'CPYTHON_G4_THREADS_PASS',
                           b'PY1_STDLIB_OK', b'PY3_A1_OK', b'PY3_A1_STATISTICS passed'):
                require(marker in data, 'missing installed CPython marker: ' + repr(marker))
            require(resources(guest) == baseline, 'resource drift after installed CPython')
            data = command('exec-file /usr/bin/python3 -B /tests/missing.py', b'kind=exited code=', 120)
            require(b'ModuleNotFoundError' in data and
                    re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', data) == [b'1'],
                    'missing module exit differs')
            require(resources(guest) == baseline, 'resource drift after missing module')
            report['checks'].append('reboot_exec_disk_stdlib_and_real_module_operations')
            if zlib:
                data = command('exec-file /usr/bin/python3 -B /tests/zlib.py', b'kind=exited code=', 180)
                require(b'PY3_A2_OK zlib streaming gzip deflate_zip zipimport truncated corrupted crc' in data
                        and re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', data) == [b'0']
                        and resources(guest) == baseline, 'installed zlib regression or resource drift')
                report['checks'].append('reboot_exec_zlib_gzip_deflated_zip_and_import')
            data = command('maint-run /usr/bin/xypm remove ' + PACKAGE,
                           b'maintenance: completed', args.maintenance_timeout)
            require(b'committed transaction cleaned' in data and resources(guest) == baseline,
                    'remove cleanup or resource recovery failed')
            guest.close()
            (output / 'run_remove.log').write_bytes(guest.output)
            guest = None
            require(check_packages(disk, profile, expected_packages)['files'] == stock_files,
                    'remaining stock package files differ')
            with Disk(disk, work, True) as fat:
                for item in managed:
                    require(fat.info('/' + item['path']) is None, 'managed file remains: ' + item['path'])
                for path in ('/var/lib/xypm/transaction', '/var/lib/xypm/txdata'):
                    require(fat.info(path) is None, 'package transaction remains: ' + path)
                expected = 'A1 pathlib 雪'.encode()
                require(fat.export('/work/user.txt').read_bytes() == user_file.read_bytes()
                        and fat.export('/work/py3a1/data/note.txt').read_bytes() == expected,
                        'user data changed')
                with zipfile.ZipFile(BytesIO(fat.export('/work/py3a1/data/stored.zip').read_bytes())) as bundle:
                    require(bundle.read('note.txt') == expected, 'user ZIP output changed')
                report['preserved_data'] = {path: sha_file(fat.export(path)) for path in
                                            ('/work/user.txt', '/work/py3a1/data/note.txt',
                                             '/work/py3a1/data/stored.zip')}
                if zlib:
                    payload = (b'XOS zlib static profile / deflate / CRC / ' + bytes(range(64))) * 300
                    gzip_path, zip_path = '/work/py3a2/payload.gz', '/work/py3a2/payload.zip'
                    compressed = fat.export(gzip_path).read_bytes()
                    archived = fat.export(zip_path).read_bytes()
                    require(gzip.decompress(compressed) == payload, 'user gzip output changed')
                    with zipfile.ZipFile(BytesIO(archived)) as bundle:
                        require(all(entry.compress_type == zipfile.ZIP_DEFLATED for entry in bundle.infolist())
                                and bundle.read('payload.bin') == payload
                                and bundle.read('py3a2_zipmod.py') == b"VALUE = 'zipimport works'\n",
                                'user deflated ZIP output changed')
                    report['preserved_data'].update({path: sha_file(fat.export(path)) for path in (gzip_path, zip_path)})
            if stock:
                report['final_disk_sha256'] = sha_file(disk)
            report['checks'].append('native_p2_remove_preserves_user_and_python_outputs')
            verify_inputs()
            report['status'] = 'passed_subset'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if guest:
            guest.close()
            (output / 'failed.log').write_bytes(guest.output)
        (output / 'report.json').write_bytes(canonical(report))


if __name__ == '__main__':
    main()
