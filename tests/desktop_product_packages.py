#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Install private product packages and run both installed applications in XOS."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_smoke import Guest
from graphics_guest import start_graphics, stop_graphics
from make_work_disk import create_fat32
from process_smoke import resources
from task_smoke import pump, send_bytes
from xypm_format import canonical, load_json, require, sha_file, verify_package
from xypm_image import Disk


def press(guest, key, modifier=None):
    codes = [modifier, key] if modifier else [key]
    for down, keys in ((True, codes), (False, reversed(codes))):
        guest.qmp('input-send-event', {'events': [
            {'type': 'key', 'data': {'down': down, 'key': {'type': 'qcode', 'data': code}}}
            for code in keys]})
    pump(guest, .1)


def guest_products(image, disk, output, checks):
    guest = Guest(image, 'products', work_disk=disk, iso=True, log_dir=output)
    try:
        guest.expect(b'xos64> ', timeout=45)
        send_bytes(guest, b'run\r')
        guest.expect_supervisor(trace=True, timeout=45)
        pump(guest, 1.5)
        baseline = resources(guest)
        graphics = start_graphics(guest)
        active = resources(guest)
        products = (
            ('mobius', b'DESKTOP_READY', 'q', 'ctrl'),
            ('clarke', b'BROWSER_CSS_LOADED path=/web/theme.css', 'esc', None),
        )
        for name, marker, key, modifier in products:
            start = len(guest.output)
            send_bytes(guest, f'exec-file /usr/bin/{name}.elf\r'.encode())
            guest.expect(marker, start=start, timeout=90)
            if name == 'clarke':
                guest.expect(b'BROWSER_LOADED path=/web/start.html', start=start, timeout=30)
            press(guest, key, modifier)
            guest.expect(b'kind=exited code=0', start=start, timeout=45)
            guest.expect_supervisor(start=start, timeout=45)
            require(resources(guest) == active, f'{name} xsh resource drift')
            checks.append(name + '_xsh')
        start = len(guest.output)
        send_bytes(guest, b'exec-driver /usr/bin/dash /desktop-products.sh\r')
        for name, marker, key, modifier in products:
            guest.expect(marker, start=start, timeout=90)
            if name == 'clarke':
                guest.expect(b'BROWSER_LOADED path=/web/start.html', start=start, timeout=30)
            press(guest, key, modifier)
            guest.expect(f'{name.upper()}_STATUS:0'.encode(), start=start, timeout=45)
            checks.append(name + '_dash')
        guest.expect_supervisor(start=start, timeout=45)
        require(resources(guest) == active, 'dash resource drift')
        stop_graphics(guest, *graphics)
        require(resources(guest) == baseline, 'graphics resource drift')
        return {'idle': baseline, 'graphics_active': active}
    finally:
        guest.close()
        (output / 'serial.log').write_bytes(guest.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'profile', 'dash-receipt', 'mobius', 'clarke', 'clarke-update', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    profile = load_json(args.profile)
    metadata = load_json(args.system / 'manifest.json')
    image = (args.system / 'xos-install.iso').resolve()
    require(sha_file(image) == metadata['artifacts']['xos-install.iso']['sha256'], 'system image mismatch')
    dash_receipt = load_json(args.dash_receipt)
    dash = ROOT / dash_receipt['elf']
    require(sha_file(dash) == dash_receipt['sha256'], 'dash ELF mismatch')
    require(dash_receipt['sdk_manifest_sha256'] == sha_file(args.system / 'sdk/manifest.json'),
            'dash was built for a different SDK')
    packages = [verify_package(path, profile) for path in (args.mobius, args.clarke, args.clarke_update)]
    manifests = [package['manifest'] for package in packages]
    require([entry['id'] for entry in manifests] == ['xos.mobius', 'xos.clarke', 'xos.clarke'],
            'unexpected package IDs')
    require(manifests[2]['revision'] > manifests[1]['revision'], 'ClarkE update must advance revision')
    checks, transactions = [], []
    report = {'status': 'failed', 'build_id': metadata['build_id'], 'image_sha256': sha_file(image),
              'system_manifest_sha256': sha_file(args.system / 'manifest.json'),
              'runner_sha256': sha_file(Path(__file__)),
              'dash_sha256': sha_file(dash), 'profile_sha256': sha_file(args.profile),
              'packages': [package['sha256'] for package in packages],
              'checks': checks, 'transactions': transactions}

    def xypm(*arguments):
        command = [sys.executable, str(ROOT / 'scripts/xypm.py'), *map(str, arguments),
                   '--profile', str(args.profile)]
        return json.loads(subprocess.check_output(command, text=True))

    try:
        with tempfile.TemporaryDirectory(prefix='xos_products_') as temporary:
            workspace = Path(temporary)
            disk = workspace / 'initial.img'
            create_fat32(disk, 512)
            legacy = workspace / 'previous-user-file'
            legacy.write_bytes(b'legacy product file controlled by the user\n')
            script = workspace / 'products.sh'
            script.write_text('/usr/bin/mobius.elf\necho MOBIUS_STATUS:$?\n'
                              '/usr/bin/clarke.elf\necho CLARKE_STATUS:$?\n')
            with Disk(disk, workspace) as volume:
                for path in ('/bin', '/usr', '/usr/bin'):
                    volume.command('mkdir', path)
                volume.command('import', '/bin/browser.elf', legacy)
                volume.command('import', '/usr/bin/dash', dash)
                volume.command('import', '/desktop-products.sh', script)

            def mutate(action, payload):
                nonlocal disk
                updated = workspace / f'{len(transactions)}.img'
                result = xypm(action, payload, '--image', disk, '--output-image', updated, '--offline')
                transactions.append(result)
                disk.unlink()
                disk = updated

            mutate('install', args.mobius)
            mutate('install', args.clarke)
            mutate('upgrade', args.clarke_update)
            installed = xypm('info', 'xos.clarke', '--image', disk)['manifest']
            require(installed['revision'] == manifests[2]['revision'],
                    'wrong ClarkE revision after upgrade')
            xypm('verify-installed', '--image', disk)
            checks.append('independent_installs_and_clarke_upgrade')
            report['resources'] = guest_products(image, disk, output, checks)
            mutate('remove', 'xos.clarke')
            xypm('verify-installed', '--image', disk)
            with Disk(disk, workspace, True) as volume:
                require(volume.info('/usr/bin/mobius.elf') is not None, 'ClarkE removal damaged Mobius')
                require(volume.info('/usr/bin/clarke.elf') is None, 'ClarkE executable survived removal')
                require(volume.info('/usr/share/xos.clarke/web/start.html') is None, 'ClarkE built-in survived removal')
            mutate('remove', 'xos.mobius')
            require(xypm('verify-installed', '--image', disk)['files'] == 0, 'managed payload survived removal')
            with Disk(disk, workspace, True) as volume:
                require(volume.export('/bin/browser.elf').read_bytes() == legacy.read_bytes(),
                        'legacy user file changed')
                require(volume.info('/usr/bin/mobius-session.elf') is None, 'Mobius session survived removal')
            checks.append('independent_removals_preserve_legacy_file')
            report['status'] = 'passed'
    finally:
        serial = output / 'serial.log'
        if serial.is_file():
            report['serial_sha256'] = sha_file(serial)
        (output / 'report.json').write_bytes(canonical(report))


if __name__ == '__main__':
    main()
