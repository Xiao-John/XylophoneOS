#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify IPC authority, deterministic blocked revocation, and service restart."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_ipc_exec_probe import INPUTS
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from work_disk import transfer
from xos_app import tree_receipt
from process_wait_any_guest import system_identity, verify_system_identity


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeat', type=int, default=3, choices=range(1, 17))
    parser.add_argument('--serial-only', action='store_true')
    args = parser.parse_args()
    system, fixture, out = args.system.resolve(), args.fixture.resolve(), args.output.absolute()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'not_run', 'runner_sha256': sha(Path(__file__)), 'checks': [],
              'not_run': ['sys81_explicit_channel_inheritance_stress', 'terminal_display_interactium_regression']}
    guest = None

    def verify_inputs():
        verify_system_identity(system, identity)
        if sha(fixture / 'receipt.json') != receipt_hash:
            raise ValueError('fixture receipt changed during acceptance')
        for name, digest in manifest['sources'].items():
            if sha(ROOT / name) != digest:
                raise ValueError('system source mismatch: ' + name)
        for name, info in manifest['artifacts'].items():
            if sha(system / name) != info['sha256']:
                raise ValueError('system artifact mismatch: ' + name)
        if receipt['sources'] != {name: sha(ROOT / name) for name in INPUTS}:
            raise ValueError('fixture source mismatch')
        if tree_receipt(system / 'sdk')[0] != receipt['sdk_tree_sha256']:
            raise ValueError('fixture SDK mismatch')
        for name, digest in receipt['artifacts'].items():
            if sha(fixture / name) != digest:
                raise ValueError('fixture artifact mismatch: ' + name)

    try:
        identity = system_identity(system)
        manifest = json.loads((system / 'manifest.json').read_text())
        receipt_bytes = (fixture / 'receipt.json').read_bytes()
        receipt_hash = hashlib.sha256(receipt_bytes).hexdigest()
        receipt = json.loads(receipt_bytes)
        verify_inputs()
        report.update(build_id=manifest['build_id'], image_sha256=sha(system / 'xos-install.iso'),
                      system_manifest_sha256=sha(system / 'manifest.json'),
                      fixture_receipt_sha256=sha(fixture / 'receipt.json'),
                      sdk_tree_sha256=receipt['sdk_tree_sha256'], artifacts=receipt['artifacts'])
        with tempfile.TemporaryDirectory(prefix='xos_ipc_exec_') as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/ipcexec.elf', fixture / 'ipc_exec_probe.elf')
            report['initial_disk_sha256'] = sha(disk)
            guest = Guest(system / 'xos-install.iso', str(out.relative_to(ROOT / 'build')) + '/guest',
                          iso=True, work_disk=disk, qmp_enabled=not args.serial_only)
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
                nonce = secrets.token_hex(16)
                cases = {
                    'parent': [
                        b'IPC_EXEC_BLOCKED receive', b'IPC_EXEC_CHILD_PASS',
                        b'IPC_EXEC_PASS failed_commit_preserved success_revoked pending_destroyed same_pid_reconnected'],
                    'lifecycle': [marker for event in ('revoke', 'close', 'exit', 'fault', 'cancel')
                                  for marker in (
                                      ('IPC_LIFECYCLE_BLOCKED ' + event + ' receive send').encode(),
                                      ('IPC_LIFECYCLE_PASS ' + event +
                                       ' blocked_both restart_authenticated stale_tokens_denied').encode())],
                    'authority': [b'IPC_AUTHORITY_PASS subject_bound attenuated redelegated revoked reply_once quota_recovered'],
                    'quota': [b'IPC_QUOTA_PASS shared_owner_budget pending_and_accepted_counted blocked_counted failure_atomic peer_isolated recovered'],
                }
                for mode, expected in cases.items():
                    output = command(guest, 'exec-driver /bin/ipcexec.elf ' + mode + ' ' + nonce,
                                     b'kind=exited code=', timeout=90)
                    outcomes = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', output)
                    if (any(output.count(marker) != 1 for marker in expected) or outcomes != [b'0'] or
                            b'IPC_EXEC_FAIL' in output):
                        raise AssertionError(output[-8000:])
                    actual = resources(guest)
                    if actual != baseline:
                        raise AssertionError(f'resource mismatch {actual}, expected {baseline}')
                    report['checks'].append({'round': round_number, 'mode': mode, 'nonce': nonce,
                        'resources': actual, 'status': 'passed',
                        'markers': [marker.decode() for marker in expected]})
            verify_inputs()
            report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        if guest:
            guest.close()
        report['evidence_files'] = [{'path': path.name, 'sha256': sha(path)}
                                    for path in sorted(out.glob('*')) if path.is_file() and path.name != 'report.json']
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS IPC exec lifecycle:', len(report['checks']), 'rounds')


if __name__ == '__main__':
    main()
