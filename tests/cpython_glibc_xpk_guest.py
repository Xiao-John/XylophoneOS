# SPDX-License-Identifier: Apache-2.0
"""Qualify native XPK install, disk stdlib, reboot and removal of glibc CPython."""

import argparse
from io import BytesIO
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from glibc_static_guest import system_sources
from make_work_disk import create_fat32
from package_cpython_glibc import LANDMARK, LIBRARY, PACKAGE, PROGRAM, RECEIPT
from package_p2_faults import boot_maintenance_guest, resources
from task_smoke import send_bytes
from xypm_format import DEFAULT_PROFILE, canonical, load_json, require, sha_file, strict_json, verify_package
from xypm_image import Disk, query_image
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
    parser.add_argument('--maintenance-timeout', type=int, default=600)
    args = parser.parse_args()
    if args.maintenance_timeout <= 0:
        parser.error('maintenance timeout must be positive')
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

    verify_inputs()
    report = {'status': 'failed', 'system_build_id': sysmeta['build_id'],
              'image_sha256': sha_file(image), 'system_manifest_sha256': sha_file(sys_path),
              'sdk_manifest_sha256': sdk_digest, 'profile_sha256': profile_digest,
              'package_sha256': package['sha256'], 'xypm_elf_sha256': sha_file(manager),
              'xypm_receipt_sha256': sha_file(manager_receipt_path),
              'cli_build_receipt_sha256': sha_file(cli_build), 'interpreter': receipt['interpreter'],
              'library_sha256': receipt['library']['sha256'],
              'stdlib_members': len(receipt['library']['members']), 'checks': []}
    guest = None
    try:
        try:
            verify_package(args.package, load_json(DEFAULT_PROFILE))
        except ValueError as error:
            require('target profile mismatch' in str(error), 'unexpected legacy profile rejection')
        else:
            raise ValueError('legacy profile admitted the glibc CPython package')
        report['checks'].append('frozen_newlib_profile_rejected')
        with tempfile.TemporaryDirectory(prefix='cpython_glibc_p2_') as folder:
            work = Path(folder)
            disk = work / 'work.img'
            create_fat32(disk, 512)
            user_file = work / 'user.txt'
            user_file.write_text('pre-existing user data\n')
            fixtures = ROOT / 'tests/fixtures'
            files = {
                '/usr/bin/xypm': manager, '/out/cpython.xpk': args.package,
                '/work/user.txt': user_file,
                '/tests/stdlib.py': fixtures / 'cpython_glibc/installed_stdlib.py',
                '/tests/startup.py': fixtures / 'cpython_glibc/startup_probe.py',
                '/tests/py1.py': fixtures / 'cpython_py1/stdlib_probe.py',
                '/tests/a1.py': fixtures / 'cpython_py3_a1/stdlib_probe.py',
                '/tests/missing.py': fixtures / 'cpython_py1/missing_import.py',
            }
            with Disk(disk, work) as fat:
                for path in ('/usr', '/usr/bin', '/out', '/work', '/work/py3a1', '/tests'):
                    fat.command('mkdir', path)
                for path, source in files.items():
                    fat.command('import', path, source)

            def command(line, success, timeout):
                start = len(guest.output)
                send_bytes(guest, line.encode() + b'\r')
                result = guest.expect_any((success, b'maintenance: retained',
                                           b'maintenance: busy or denied'), start=start, timeout=timeout)
                require(result == success, 'maintenance failed: ' + line)
                guest.expect_supervisor(start=start, timeout=40)
                return bytes(guest.output[start:])

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
            report['installed_files'] = query_image(disk, profile, 'verify-installed')['files']
            require(report['installed_files'] == len(managed), 'installed files differ')

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
            data = command('maint-run /usr/bin/xypm remove ' + PACKAGE,
                           b'maintenance: completed', args.maintenance_timeout)
            require(b'committed transaction cleaned' in data and resources(guest) == baseline,
                    'remove cleanup or resource recovery failed')
            guest.close()
            (output / 'run_remove.log').write_bytes(guest.output)
            guest = None
            require(query_image(disk, profile, 'list')['packages'] == [], 'CPython remains installed')
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
