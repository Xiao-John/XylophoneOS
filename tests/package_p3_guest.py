#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check native offline repositories and single-package transactions in XOS."""
import argparse
import hashlib
import json
from pathlib import Path
import re

import package_p3_repository as fixtures
from package_p1_guest import Disk, Guest, ROOT, create_fat32, pump, resources, send_bytes
from xypm_format import canonical, load_json, require, sha_file
from xypm_repository import create_repository, make_lock, write_metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'profile', 'sdk', 'xypm-build', 'dash-manifest', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
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
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'build_id': system['build_id'], 'image_sha256': sha_file(image),
              'system_manifest_sha256': sha_file(args.system / 'manifest.json'),
              'profile_sha256': sha_file(args.profile), 'sdk_tree_sha256': sdk['tree_sha256'],
              'xypm_sha256': sha_file(elf), 'dash_sha256': dash['sha256'], 'checks': []}
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
        with Disk(disk, case.folder) as backend:
            for name in ('/usr', '/usr/bin', '/repo', '/next'):
                backend.command('mkdir', name)
            for repo, dest in ((case.repository, '/repo'), (next_repo, '/next')):
                for item in repo.rglob('*'):
                    if item.is_file():
                        backend.command('import', dest + '/' + item.relative_to(repo).as_posix(), item)
            backend.command('import', '/lock.json', case.lock_path)
            backend.command('import', '/next.json', next_lock)
            backend.command('import', '/usr/bin/xypm', elf)
            backend.command('import', '/usr/bin/dash', dash_elf)
            shell = case.folder / 'check.sh'
            shell.write_text('set -e\n/usr/bin/xypm repo-plan /repo /lock.json\n'
                             '/usr/bin/xypm repo-verify /repo /lock.json --lock-sha256 ' + '0' * 64 +
                             ' && exit 1\n/usr/bin/xypm repo-verify /repo /lock.json\n')
            backend.command('import', '/check.sh', shell)
        report['disk_initial_sha256'] = sha_file(disk)
        guest = Guest(image, 'package_p3_guest', work_disk=disk, iso=True)
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
            if code is not None:
                statuses = re.findall(rb'kind=exited code=(-?\d+)', data)
                require(statuses and int(statuses[-1]) == code, repr(data[-2000:]))
            if marker is not None:
                require(marker in data, repr(data[-2000:]))
            require(resources(guest) == baseline, 'resource drift after ' + line)
            report['checks'].append(line)

        command('xypm repo-verify /repo /lock.json --lock-sha256 ' + report['locks'][0], 0)
        command('dash /check.sh', 0, b'Dependency-first lock order')
        command('xypm repo-install /repo /lock.json friends.base', 3, b'maintenance write lease required')
        command('maint-run /usr/bin/xypm repo-install /repo /lock.json friends.base', marker=b'maintenance: completed')
        command('maint-run /usr/bin/xypm repo-install /repo /lock.json friends.app', marker=b'maintenance: completed')
        command('xypm list', 0, b'friends.app 1.0-r0')
        command('maint-run /usr/bin/xypm repo-upgrade /next /next.json friends.app', marker=b'maintenance: completed')
        command('xypm list', 0, b'friends.app 1.0-r1')
        command('maint-run /usr/bin/xypm remove friends.app', marker=b'maintenance: completed')
        command('xypm info friends.app', 1, b'package not installed')
        command('sync', marker=b'[files] sync=ok')
        guest.close()
        (args.output / 'first_serial.log').write_bytes(guest.output)
        guest = Guest(image, 'package_p3_reboot', work_disk=disk, iso=True)
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
        report['disk_final_sha256'] = sha_file(disk)
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
