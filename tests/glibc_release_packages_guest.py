# SPDX-License-Identifier: Apache-2.0
"""Run the shared release Python smoke and reclaim packages on the composed disk."""
from pathlib import Path
import subprocess

from boot_smoke import Guest
from package_glibc_release import IMAGES, INSTALLER, MANIFEST, ORDINARY, verify_assembled, verify_disk
from package_p2_faults import resources, sparse_copy
from package_p2_verify_guest import quiet_maintenance_guest
from task_smoke import send_bytes
from xypm_format import canonical, require, sha_file, verify_package
from xypm_image import Disk

PYTHON_OK = b'RELEASE_PY3_THREADS_JSON_ZLIB_IDNA_OK'
USER_PATH = '/out/release_user.txt'
USER_DATA = b'release user data survives package cleanup\n'
REMAINS_OK = '''import gzip
assert gzip.decompress(gzip.compress(b'XOS')) == b'XOS'
try:
    import idna
except ModuleNotFoundError as error:
    assert error.name == 'idna'
else:
    raise AssertionError('uninstalled IDNA remains importable')
print('RELEASE_CPYTHON_RETAINED_IDNA_REMOVED_OK')
'''


def command(guest, line, expected, timeout=120):
    offset = len(guest.output)
    send_bytes(guest, line.encode() + b'\r')
    found = guest.expect_any((expected, b'xsh> '), start=offset, timeout=timeout)
    require(found == expected, 'unexpected guest result for ' + line)
    guest.expect_supervisor(start=offset, timeout=timeout)
    return bytes(guest.output[offset:])


def python_smoke(guest, baseline, path, marker):
    output = command(guest, 'exec-file /usr/bin/python3 -B ' + path, b'kind=exited code=0', timeout=180)
    require(marker in output and resources(guest) == baseline, 'release Python smoke or resource check failed')


def boot(image, disk, output, role, build_id):
    guest = Guest(image, role, work_disk=disk, iso=True, log_dir=output)
    try:
        guest.expect(b'xos64> ', timeout=60)
        require(b'build=' + build_id.encode() in guest.output, 'release guest build differs')
        send_bytes(guest, b'run\r')
        if role == 'installer':
            guest.expect(b'[files] bundle packages installed', timeout=600)
        guest.expect_supervisor(trace=True, timeout=60)
        quiet_maintenance_guest(guest)
        return guest
    except BaseException:
        guest.close()
        raise


def run(release_root, output, foreign, python_source):
    release, profile = verify_assembled(release_root)
    packages = release['packages']
    require('wheel' in packages, 'combined Python smoke requires the IDNA wheel')
    output.mkdir(parents=True, exist_ok=False)
    images = release_root / IMAGES
    source_disk = images / 'work_disk.img'
    disk = output / 'work.img'
    report = {'status': 'failed', 'checks': [], 'build_id': release['system']['build_id'],
              'release_manifest_sha256': sha_file(release_root / MANIFEST),
              'installer_iso_sha256': release['installer_iso']['sha256'],
              'ordinary_iso_sha256': release['system']['iso']['sha256'],
              'assembled_disk_sha256': release['work_disk']['sha256'],
              'profile_sha256': release['application_sdk']['profile_sha256'], 'packages': packages}
    guest = None
    try:
        if foreign:
            checked_foreign = verify_package(foreign)
            require(checked_foreign['manifest']['target_profile'] != profile['id'], 'expected a foreign XPK')
            report['foreign_package_sha256'] = checked_foreign['sha256']
        sparse_copy(source_disk, disk)
        require(sha_file(disk) == release['work_disk']['sha256'], 'release disk copy differs')
        with Disk(disk, output) as fat:
            require(all(fat.info('/usr/bin/' + name) is None for name in ('dash', 'xypm')),
                    'installer binaries unexpectedly preseeded')
            for name, contents in (('release.py', python_source.encode()), ('remaining.py', REMAINS_OK.encode()),
                                   ('release_user.txt', USER_DATA)):
                fixture = output / name
                fixture.write_bytes(contents)
                fat.command('import', '/out/' + name, fixture)
            if foreign:
                fat.command('import', '/out/foreign.xpk', foreign)
        report['python_fixture_sha256'] = sha_file(output / 'release.py')
        report['initial_disk'] = verify_disk(disk, profile, packages)
        guest = boot(images / INSTALLER, disk, output, 'installer', report['build_id'])
        report['qemu'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
        report['installer_resources'] = resources(guest)
        python_smoke(guest, report['installer_resources'], '/out/release.py', PYTHON_OK)
        command(guest, 'sync', b'[files] sync=ok')
        guest.close()
        guest = None
        report['installed_disk'] = verify_disk(disk, profile, packages)
        with Disk(disk, output, True) as fat:
            require(all(sha_file(fat.export('/usr/bin/' + name)) == release[name + '_sha256']
                        for name in ('dash', 'xypm')), 'ISO-installed files differ from installer receipt')
        sparse_copy(disk, output / 'after_installer.img')
        report['checks'].append('installer_idempotent_package_setup_and_python_smoke')

        guest = boot(images / ORDINARY, disk, output, 'ordinary', report['build_id'])
        baseline = resources(guest)
        report['ordinary_resources'] = baseline
        python_smoke(guest, baseline, '/out/release.py', PYTHON_OK)
        command(guest, 'exec-file /usr/bin/xypm info python_idna', b'id: python_idna')
        report['checks'].append('cold_ordinary_python_and_native_ownership')
        if foreign:
            refused = command(guest, 'maint-run /usr/bin/xypm install /out/foreign.xpk', b'maintenance: retained')
            require(b'package target profile differs from this xypm build' in refused, 'unexpected foreign XPK result')
            recovered = command(guest, 'maint-recover-boot', b'maintenance: completed')
            require(b'xypm-recover: no transaction' in recovered and resources(guest) == baseline,
                    'foreign XPK left state or resources')
            report['checks'].append('native_foreign_package_rejected_without_transaction')
        for name in ('wheel', 'daily'):
            removed = command(guest, 'maint-run /usr/bin/xypm remove ' + packages[name]['id'],
                              b'maintenance: completed', timeout=900)
            require(b'committed transaction cleaned' in removed and resources(guest) == baseline,
                    'native package removal left state or resources')
        python_smoke(guest, baseline, '/out/remaining.py', b'RELEASE_CPYTHON_RETAINED_IDNA_REMOVED_OK')
        command(guest, 'sync', b'[files] sync=ok')
        guest.close()
        guest = None
        report['remaining_disk'] = verify_disk(disk, profile, {'cpython': packages['cpython']})
        with Disk(disk, output, True) as fat:
            for name in ('wheel', 'daily'):
                archive = verify_package(release_root / 'packages' / (name + '.xpk'), profile,
                                         expected_sha256=packages[name]['sha256'])
                require(all(fat.info('/' + item['path']) is None for item in archive['manifest']['files']),
                        'removed package left an owned file')
            require(all(fat.info('/var/lib/xypm/' + name) is None
                        for name in ('transaction', 'transaction_commit', 'txdata')), 'transaction remains after removal')
            user = fat.export(USER_PATH)
            require(user.read_bytes() == USER_DATA, 'release user data changed')
            report['preserved_user_sha256'] = sha_file(user)
        require(sha_file(source_disk) == release['work_disk']['sha256'], 'published assembly disk was written')
        report['final_disk_sha256'] = sha_file(disk)
        report['checks'].append('native_daily_and_wheel_reclaimed_python_and_user_data_retained')
        report['status'] = 'passed_subset'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if guest is not None:
            guest.close()
        (output / 'report.json').write_bytes(canonical(report))
