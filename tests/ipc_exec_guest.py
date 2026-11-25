#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise IPC revocation with failed and successful exec in a real guest."""
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
        manifest = json.loads((system / 'manifest.json').read_text())
        receipt = json.loads((fixture / 'receipt.json').read_text())
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
            pump(guest, 0.2)
            baseline = resources(guest)
            report['baseline'] = baseline
            for round_number in range(args.repeat):
                nonce = secrets.token_hex(16)
                output = command(guest, 'exec-driver /bin/ipcexec.elf parent ' + nonce,
                                 b'kind=exited code=', timeout=45)
                expected = b'IPC_EXEC_PASS failed_commit_preserved success_revoked pending_destroyed same_pid_reconnected'
                if (expected not in output or b'IPC_EXEC_CHILD_PASS' not in output or
                    not re.search(rb'\[wait\].*kind=exited code=0', output) or b'IPC_EXEC_FAIL' in output):
                    raise AssertionError(output[-5000:])
                actual = resources(guest)
                if actual != baseline:
                    raise AssertionError(f'resource mismatch {actual}, expected {baseline}')
                report['checks'].append({'round': round_number, 'nonce': nonce, 'resources': actual,
                    'status': 'passed', 'scope': ['failed_exec_preserves_name_and_channel',
                    'successful_exec_revokes_both_endpoints', 'blocked_peer_wakes',
                    'old_name_removed', 'queued_unaccepted_connection_discarded',
                    'same_pid_new_tokens_authenticated', 'child_exit_reclaims_everything']})
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
