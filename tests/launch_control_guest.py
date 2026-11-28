#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run authenticated READY/exec/wait cases against actual kernel channels."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_launch_control_probe import INPUTS
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from work_disk import transfer
from xos_app import tree_receipt

CASES = ('success', 'cancel', 'entry-failure', 'entry-revoke', 'prepare-revoke',
         'timeout', 'early-exit', 'malformed', 'multiple', 'stale-allow', 'stale-cancel')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'fixture', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--repeat', type=int, choices=range(1, 9), default=3)
    args = parser.parse_args()
    system, fixture, out = args.system.resolve(), args.fixture.resolve(), args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'runs': [], 'runner_sha256': sha(Path(__file__))}
    guest = None
    try:
        manifest = json.loads((system / 'manifest.json').read_bytes())
        receipt = json.loads((fixture / 'receipt.json').read_bytes())

        def verify_inputs():
            for path, digest in manifest['sources'].items():
                if sha(ROOT / path) != digest:
                    raise ValueError('system source changed: ' + path)
            for path, value in manifest['artifacts'].items():
                if sha(system / path) != value['sha256']:
                    raise ValueError('system artifact changed: ' + path)
            if receipt['sources'] != {path: sha(ROOT / path) for path in INPUTS}:
                raise ValueError('fixture source changed')
            if tree_receipt(system / 'sdk')[0] != receipt['sdk_tree_sha256']:
                raise ValueError('fixture SDK changed')
            for path, digest in receipt['artifacts'].items():
                if sha(fixture / path) != digest:
                    raise ValueError('fixture artifact changed')

        verify_inputs()
        report.update(system_build_id=manifest['build_id'], iso_sha256=sha(system / 'xos-install.iso'),
                      system_manifest_sha256=sha(system / 'manifest.json'),
                      fixture_receipt_sha256=sha(fixture / 'receipt.json'), sdk_tree_sha256=receipt['sdk_tree_sha256'])
        with tempfile.TemporaryDirectory(prefix='xos_launch_guest_') as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/launch.elf', fixture / 'launch_control.elf')
            guest = Guest(system / 'xos-install.iso', 'guest', iso=True, work_disk=disk,
                          qmp_enabled=False, log_dir=out)
            report['qemu_command'] = guest.command
            guest.expect(b'xos64> ', timeout=60)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, 'demo quiet', b'demo tasks')
            command(guest, 'audio stop', b'xsh> ')
            pump(guest, 0.2)
            baseline = resources(guest)
            report['baseline'] = baseline
            for round_number in range(args.repeat):
                for mode in CASES:
                    output = command(guest, 'exec-driver /bin/launch.elf ' + mode, b'kind=exited code=', timeout=45)
                    exits = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', output)
                    if output.count(('LAUNCH_PASS ' + mode).encode()) != 1 or b'LAUNCH_FAIL' in output or exits != [b'0']:
                        raise AssertionError(output[-6000:])
                    actual = resources(guest)
                    if actual != baseline:
                        raise AssertionError(f'resources {actual}, expected {baseline}')
                    report['runs'].append({'round': round_number, 'case': mode, 'resources': actual, 'status': 'passed'})
            verify_inputs()
            report['status'] = 'passed'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        if guest:
            guest.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS launch-control guest:', len(report['runs']))


if __name__ == '__main__':
    main()
