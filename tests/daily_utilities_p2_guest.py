# SPDX-License-Identifier: Apache-2.0
"""Install daily XPK with guest xypm P2, reboot, use, and remove on a private disk."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from daily_utilities_smoke import expected_du12_outputs
from make_work_disk import create_fat32
from package_p2_faults import boot_maintenance_guest, resources
from task_smoke import send_bytes
from xypm_format import canonical, load_json, require, sha_file, strict_json, verify_package
from xypm_image import Disk, query_image
from xypm_sdk_profile import verify_profile


def check_glibc_builds(args, profile, package, daily, elf):
    binding = verify_profile(profile, 'glibc', args.glibc_sdk)
    sdk_digest = profile['sdk_binding']['sdk_manifest_sha256']
    profile_digest = binding['profile_sha256']
    manager = load_json(elf.parent / 'build_receipt.json')
    require(manager['project_id'] == 'xos.xypm' and manager['target_profile'] == profile['id'] and
            manager['runtime_family'] == 'glibc' and manager['output_sha256'] == sha_file(elf),
            'xypm executable differs from its glibc receipt')
    for receipt in (manager, daily):
        require(receipt['sdk_manifest_sha256'] == sdk_digest and
                receipt['profile_sha256'] == profile_digest and
                receipt['sdk_tree_sha256'] == binding['sdk_tree_sha256'],
                'manager and utilities must use the same glibc SDK/profile')
    wanted = load_json(ROOT / 'src/ports/sbase/daily_utilities.json')['tools']
    files = {item['path']: item['sha256'] for item in package['manifest']['files']
             if item['role'] == 'executable'}
    require(set(files) == {'usr/bin/' + tool['name'] for tool in wanted} and
            files == {tool['guest_path'].lstrip('/'): tool['elf_sha256'] for tool in daily['tools']},
            'daily XPK executable set differs from the daily build receipt')
    dash = load_json(args.dash_receipt)
    require(dash['profile'] == 'dash_glibc_preview' and dash['sdk_manifest_sha256'] == sdk_digest and
            dash['sdk_profile_binding'] == binding and dash['sha256'] == sha_file(args.dash),
            'dash executable differs from its glibc SDK/profile receipt')
    return {'sdk_manifest_sha256': sdk_digest, 'profile_binding_sha256': profile_digest,
            'xypm_receipt_sha256': sha256(canonical(manager)).hexdigest(),
            'dash_receipt_sha256': sha_file(args.dash_receipt),
            'tools': len(files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--xypm-build', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--dash', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--glibc-sdk', type=Path)
    parser.add_argument('--dash-receipt', type=Path)
    parser.add_argument('--maintenance-timeout', type=int, default=360)
    parser.add_argument('--dash-timeout', type=int, default=180)
    args = parser.parse_args()
    if min(args.maintenance_timeout, args.dash_timeout) <= 0:
        parser.error('timeouts must be positive')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    system = load_json(args.system / 'manifest.json')
    image = args.system / 'xos-install.iso'
    profile = load_json(args.profile)
    glibc = profile.get('runtime_family') == 'glibc'
    if glibc and (args.glibc_sdk is None or args.dash_receipt is None or
                  not {'cxx_runtime', 'stdio_transfer'} <= set(profile['features'])):
        parser.error('glibc requires a C/C++ stdio_transfer profile, --glibc-sdk and --dash-receipt')
    build = load_json(args.xypm_build)
    elf = Path(build['elf'])
    package = verify_package(args.package, profile)
    managed = package['manifest']
    require(sha_file(image) == system['artifacts']['xos-install.iso']['sha256'], 'system mismatch')
    require(managed['id'] == 'xos.daily_utilities' and
            build['target_profile'] == profile['id'], 'wrong package or manager profile')
    report = {'status': 'failed', 'system_build_id': system['build_id'], 'image_sha256': sha_file(image),
              'xypm_elf_sha256': sha_file(elf), 'package_sha256': package['sha256'],
              'profile_sha256': sha_file(args.profile), 'dash_sha256': sha_file(args.dash),
              'test_sha256': sha_file(__file__), 'checks': [],
              'maintenance_timeout_seconds': args.maintenance_timeout, 'dash_timeout_seconds': args.dash_timeout,
              'not_run': ['fault_injection', 'abrupt_power_loss', 'upgrade', 'iso_install']}
    guest = None
    try:
        if glibc:
            daily_bytes = bytearray()
            receipt = managed['build_receipt']

            def capture_receipt(event, item, chunk):
                if event == 'data' and item['path'] == receipt['path']:
                    daily_bytes.extend(chunk)

            require(verify_package(args.package, profile, expected_sha256=package['sha256'],
                                   sink=capture_receipt) == package and
                    sha256(daily_bytes).hexdigest() == receipt['sha256'], 'daily XPK build receipt differs')
            report['daily_receipt_sha256'] = receipt['sha256']
            report.update(check_glibc_builds(args, profile, package, strict_json(daily_bytes), elf))

        with tempfile.TemporaryDirectory(prefix='xos_du_p2_') as tmp:
            root = Path(tmp)
            disk = root / 'work.img'
            create_fat32(disk, 512)
            fixture = ROOT / 'tests/fixtures/daily_utilities'
            sentinel = root / 'sentinel'
            sentinel.write_bytes(b'user data before install\n')
            user_file = root / 'user.txt'
            user_file.write_bytes(b'user data in package directory\n')
            user_path = '/usr/share/xos.daily_utilities/user.txt'
            limit = root / 'tail_limit.dat'
            limit.write_bytes(b'a' * (1024 * 1024 - 1) + b'\nlast\n')
            over = root / 'tail_over_limit.dat'
            over.write_bytes(b'a' * (1024 * 1024 + 1))
            with Disk(disk, root) as backend:
                for path in ('/usr', '/usr/bin', '/out', '/tmp', '/tests'):
                    backend.command('mkdir', path)
                for path, source in (
                    ('/usr/bin/xypm', elf), ('/usr/bin/dash', args.dash),
                    ('/out/daily.xpk', args.package), ('/out/sentinel', sentinel),
                    ('/tests/du12.sh', fixture / 'du12.sh'), ('/tests/binary.dat', fixture / 'binary.dat'),
                    ('/tests/tail_limit.dat', limit), ('/tests/tail_over_limit.dat', over),
                ):
                    backend.command('import', path, source)

            def command(line, expected, timeout):
                start = len(guest.output)
                send_bytes(guest, line.encode() + b'\r')
                guest.expect(expected, start=start, timeout=timeout)
                guest.expect_supervisor(start=start, timeout=timeout)
                return bytes(guest.output[start:])

            guest = boot_maintenance_guest(image, 'daily_p2_install', disk)
            baseline = resources(guest)
            report['install_baseline'] = baseline
            command('xypm install /out/daily.xpk', b'maintenance write lease required', 40)
            require(resources(guest) == baseline, 'resources drift after denied install')
            report['checks'].append('ordinary_install_denied')
            data = command('maint-run /usr/bin/xypm install /out/daily.xpk --sha256 ' + package['sha256'],
                           b'maintenance: completed', args.maintenance_timeout)
            require(b'committed transaction cleaned' in data, 'install cleanup missing')
            require(resources(guest) == baseline, 'resources drift after install')
            report['checks'].append('guest_p2_install')
            guest.close()
            (out / 'install.log').write_bytes(guest.output)
            guest = None
            report['installed_files'] = query_image(disk, profile, 'verify-installed')['files']
            require(report['installed_files'] == len(managed['files']), 'installed contents mismatch')
            with Disk(disk, root) as backend:
                backend.command('import', user_path, user_file)

            guest = boot_maintenance_guest(image, 'daily_p2_reboot', disk)
            baseline = resources(guest)
            report['run_remove_baseline'] = baseline
            command('dash /tests/du12.sh', b'DU12_OK', args.dash_timeout)
            require(resources(guest) == baseline, 'resources drift after utilities')
            command('sync', b'xsh> ', 40)
            report['checks'].append('reboot_and_installed_tools')
            data = command('maint-run /usr/bin/xypm remove xos.daily_utilities',
                           b'maintenance: completed', args.maintenance_timeout)
            require(b'committed transaction cleaned' in data, 'remove cleanup missing')
            require(resources(guest) == baseline, 'resources drift after remove')
            guest.close()
            (out / 'run_remove.log').write_bytes(guest.output)
            guest = None
            require(query_image(disk, profile, 'list')['packages'] == [], 'package remains')
            with Disk(disk, root, True) as backend:
                for item in managed['files']:
                    require(backend.info('/' + item['path']) is None, 'managed file remains: ' + item['path'])
                for path in ('/var/lib/xypm/transaction', '/var/lib/xypm/txdata'):
                    require(backend.info(path) is None, 'transaction state remains: ' + path)
                require(backend.export('/out/sentinel').read_bytes() == sentinel.read_bytes() and
                        backend.export(user_path).read_bytes() == user_file.read_bytes(),
                        'user data changed')
                expected = expected_du12_outputs()
                for name, contents in expected.items():
                    require(backend.export('/tmp/du/' + name).read_bytes() == contents,
                            'DU12 output differs: ' + name)
            report['checked_output_files'] = len(expected)
            report['checks'].append('guest_p2_remove_preserves_user_data_and_exact_du12_outputs')
            report['status'] = 'passed'
    except Exception as error:
        report['error'] = str(error)
        if guest:
            report['output_tail'] = bytes(guest.output[-12000:]).decode(errors='replace')
        raise
    finally:
        if guest:
            guest.close()
            (out / 'failed.log').write_bytes(guest.output)
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
