#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check native offline repositories and single-package transactions in XOS."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

import package_p3_repository as fixtures
from package_p1_guest import Disk, Guest, ROOT, create_fat32, pump, resources, send_bytes
from xypm_format import canonical, load_json, require, sha_file
from xypm_repository import create_repository, make_lock, write_metadata
from xypm_image import query_image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'profile', 'sdk', 'xypm-build', 'dash-manifest', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--serial-only', action='store_true',
                        help='disable the unused QMP socket for restricted hosts')
    args = parser.parse_args()
    image = args.system / 'xos-install.iso'
    system = load_json(args.system / 'manifest.json')
    require(sha_file(image) == system['artifacts']['xos-install.iso']['sha256'], 'image mismatch')
    for name, digest in system['sources'].items():
        require(sha_file(ROOT / name) == digest, 'system source mismatch: ' + name)
    build = load_json(args.xypm_build)
    dash = load_json(args.dash_manifest)
    elf, dash_elf = Path(build['elf']), ROOT / dash['elf']
    require(sha_file(build['package']) == build['sha256'], 'xypm package mismatch')
    require(sha_file(dash_elf) == dash['sha256'], 'dash mismatch')
    require(sha_file(args.system / 'sdk/manifest.json') == dash['sdk_manifest_sha256'], 'dash SDK mismatch')
    fixtures.profile = load_json(args.profile)
    from xos_app import sdk_check
    sdk = sdk_check(args.sdk, fixtures.profile)
    receipt = load_json(elf.parent / 'build_receipt.json')
    require(receipt['sdk_tree_sha256'] == sdk['tree_sha256']
            and receipt['profile_sha256'] == hashlib.sha256(canonical(fixtures.profile)).hexdigest(),
            'xypm SDK/profile mismatch')
    require(receipt['output_sha256'] == sha_file(elf), 'xypm ELF mismatch')
    input_files = {str(Path(path).resolve()): sha_file(path) for path in (
        args.system / 'manifest.json', image, args.profile, args.xypm_build,
        args.dash_manifest, build['package'], elf, dash_elf,
        elf.parent / 'build_receipt.json', args.system / 'sdk/manifest.json')}

    def unchanged_inputs():
        for name, digest in input_files.items():
            require(sha_file(name) == digest, 'input changed during guest acceptance: ' + name)
        for name, digest in system['sources'].items():
            require(sha_file(ROOT / name) == digest, 'system source changed: ' + name)
        require(sdk_check(args.sdk, fixtures.profile)['tree_sha256'] == sdk['tree_sha256'],
                'SDK tree changed during guest acceptance')

    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'build_id': system['build_id'], 'image_sha256': sha_file(image),
              'system_manifest_sha256': sha_file(args.system / 'manifest.json'),
              'profile_sha256': sha_file(args.profile), 'sdk_tree_sha256': sdk['tree_sha256'],
              'xypm_sha256': sha_file(elf), 'dash_sha256': dash['sha256'],
              'qmp_enabled': not args.serial_only, 'checks': []}
    case = fixtures.repository_cases()
    guest = None
    try:
        case.setUp()
        disk = case.folder / 'work.img'
        create_fat32(disk, 512)
        # Separate locks select the two versions without introducing index ambiguity.
        upgraded = case.package('friends.app', revision=1, dependencies=[case.dependency])
        next_repo = case.folder / 'next'
        create_repository([case.base, upgraded], next_repo, fixtures.profile)
        next_lock = case.folder / 'next.json'
        write_metadata(next_lock, make_lock(next_repo, [sha_file(upgraded)], fixtures.profile))
        report['locks'] = [sha_file(case.lock_path), sha_file(next_lock)]
        reversed_lock = dict(case.lock, packages=list(reversed(case.lock['packages'])))
        bad_order = case.folder / 'bad_order.json'
        write_metadata(bad_order, reversed_lock)
        foreign = case.folder / 'foreign'
        shutil.copytree(case.repository, foreign)
        foreign_index = load_json(foreign / 'index.json')
        foreign_index['target_profile'] = 'other-runtime-profile'
        (foreign / 'index.json').write_bytes(canonical(foreign_index))
        changed = case.folder / 'changed'
        shutil.copytree(case.repository, changed)
        with (changed / 'index.json').open('ab') as stream:
            stream.write(b' ')
        tampered = case.folder / 'tampered'
        shutil.copytree(case.repository, tampered)
        tampered_package = tampered / (case.base_hash + '.xpk')
        damaged = bytearray(tampered_package.read_bytes())
        damaged[6000] ^= 1
        tampered_package.write_bytes(damaged)
        repository_inputs = {}
        with Disk(disk, case.folder) as backend:
            for name in ('/usr', '/usr/bin', '/repo', '/next', '/foreign', '/changed', '/tampered'):
                backend.command('mkdir', name)
            for repo, dest in ((case.repository, '/repo'), (next_repo, '/next'),
                               (foreign, '/foreign'), (changed, '/changed'), (tampered, '/tampered')):
                for item in repo.rglob('*'):
                    if item.is_file():
                        target = dest + '/' + item.relative_to(repo).as_posix()
                        backend.command('import', target, item)
                        repository_inputs[target] = sha_file(item)
            backend.command('import', '/lock.json', case.lock_path)
            backend.command('import', '/next.json', next_lock)
            backend.command('import', '/bad_order.json', bad_order)
            backend.command('import', '/usr/bin/xypm', elf)
            backend.command('import', '/usr/bin/dash', dash_elf)
            shell = case.folder / 'check.sh'
            shell.write_text('set -e\n/usr/bin/xypm repo-plan /repo /lock.json\n'
                             '/usr/bin/xypm repo-verify /repo /lock.json --lock-sha256 ' + '0' * 64 +
                             ' && exit 1\n/usr/bin/xypm repo-verify /repo /lock.json\n')
            backend.command('import', '/check.sh', shell)
        report['disk_initial_sha256'] = sha_file(disk)
        guest = Guest(image, 'package_p3_guest', work_disk=disk, iso=True,
                      qmp_enabled=not args.serial_only)
        guest.expect(b'xos64> ', timeout=40)
        send_bytes(guest, b'run\r')
        guest.expect_supervisor(trace=True, timeout=40)
        start = len(guest.output)
        send_bytes(guest, b'demo quiet\r')
        guest.expect_any((b'demo tasks stopped', b'demo tasks already stopped'), start=start, timeout=40)
        guest.expect_supervisor(start=start, timeout=40)
        start = len(guest.output)
        send_bytes(guest, b'audio stop\r')
        guest.expect(b'audio: service stopped', start=start, timeout=40)
        guest.expect_supervisor(start=start, timeout=40)
        pump(guest, 1.5)
        baseline = resources(guest)
        report['resources'] = baseline

        def command(line, code=None, marker=None):
            start = len(guest.output)
            send_bytes(guest, line.encode() + b'\r')
            guest.expect_supervisor(start=start, timeout=90)
            data = bytes(guest.output)[start:]
            statuses = re.findall(rb'kind=exited code=(-?\d+)', data)
            if code is not None:
                require(statuses and int(statuses[-1]) == code, repr(data[-2000:]))
            if marker is not None:
                require(marker in data, repr(data[-2000:]))
            after = resources(guest)
            require(after == baseline, 'resource drift after ' + line)
            report['checks'].append({'command': line, 'expected_exit_code': code,
                                     'observed_exit_codes': [int(value) for value in statuses],
                                     'expected_marker': marker.decode() if marker else None,
                                     'resources': after, 'output_sha256': hashlib.sha256(data).hexdigest()})

        command('xypm repo-verify /repo /lock.json --lock-sha256 ' + report['locks'][0], 0)
        command('xypm repo-verify /repo /lock.json --lock-sha256 ' + '0' * 64,
                3, b'lock SHA-256 mismatch')
        command('xypm repo-verify /repo /bad_order.json', 3,
                b'lock is not the exact deterministic dependency closure')
        command('xypm repo-verify /foreign /lock.json', 3, b'repository target profile mismatch')
        command('xypm repo-verify /changed /lock.json', 3, b'lock/index SHA-256 mismatch')
        command('xypm repo-verify /tampered /lock.json', 3, b'repository rejected')
        command('dash /check.sh', 0, b'Dependency-first lock order')
        command('xypm repo-install /repo /lock.json friends.base', 3, b'maintenance write lease required')
        command('xypm plan install /repo/' + case.application_hash + '.xpk',
                3, b'package dependency is missing')
        command('maint-run /usr/bin/xypm repo-install /repo /lock.json friends.base', marker=b'maintenance: completed')
        command('maint-run /usr/bin/xypm repo-install /repo /lock.json friends.app', marker=b'maintenance: completed')
        command('xypm list', 0, b'friends.app 1.0-r0')
        command('xypm plan remove friends.base', 3, b'installed package depends on removal target')
        command('maint-run /usr/bin/xypm repo-upgrade /next /next.json friends.app', marker=b'maintenance: completed')
        command('xypm list', 0, b'friends.app 1.0-r1')
        command('maint-run /usr/bin/xypm remove friends.app', marker=b'maintenance: completed')
        command('xypm info friends.app', 1, b'package not installed')
        command('sync', marker=b'[files] sync=ok')
        guest.close()
        (args.output / 'first_serial.log').write_bytes(guest.output)
        guest = None
        report['first_disk_sha256'] = sha_file(disk)
        report['first_installed'] = query_image(disk, fixtures.profile)
        require([item['id'] for item in report['first_installed']['packages']] == ['friends.base'],
                'unexpected installed packages after transactions')
        report['first_verification'] = query_image(disk, fixtures.profile, 'verify-installed')
        guest = Guest(image, 'package_p3_reboot', work_disk=disk, iso=True,
                      qmp_enabled=not args.serial_only)
        guest.expect(b'xos64> ', timeout=40)
        send_bytes(guest, b'run\r')
        guest.expect_supervisor(trace=True, timeout=40)
        start = len(guest.output)
        send_bytes(guest, b'demo quiet\r')
        guest.expect_any((b'demo tasks stopped', b'demo tasks already stopped'), start=start, timeout=40)
        guest.expect_supervisor(start=start, timeout=40)
        start = len(guest.output)
        send_bytes(guest, b'audio stop\r')
        guest.expect(b'audio: service stopped', start=start, timeout=40)
        guest.expect_supervisor(start=start, timeout=40)
        pump(guest, 1.5)
        require(resources(guest) == baseline, 'resource drift after reboot')
        command('xypm list', 0, b'friends.base 1.0-r0')
        command('xypm info friends.app', 1, b'package not installed')
        guest.close()
        (args.output / 'serial.log').write_bytes(guest.output)
        guest = None
        report['final_installed'] = query_image(disk, fixtures.profile)
        require(report['final_installed'] == report['first_installed'], 'installed state changed on reboot')
        report['final_verification'] = query_image(disk, fixtures.profile, 'verify-installed')
        with Disk(disk, case.folder, True) as backend:
            require(backend.info('/usr/share/friends.app/data') is None, 'removed payload survived')
            for name, digest in repository_inputs.items():
                require(sha_file(backend.export(name)) == digest, 'repository input changed: ' + name)
        report['repository_inputs_preserved'] = len(repository_inputs)
        report['disk_final_sha256'] = sha_file(disk)
        unchanged_inputs()
        report['immutable_inputs_verified'] = True
        report['status'] = 'passed_subset'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if guest:
            guest.close()
            (args.output / 'serial.log').write_bytes(guest.output)
        case.tearDown()
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS P3 offline repository guest subset')


if __name__ == '__main__':
    main()
