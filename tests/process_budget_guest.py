#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real cumulative-budget syscalls, Files reply loss, and competing controller threads."""
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
from build_process_budget_probe import INPUTS
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from work_disk import transfer
from xos_app import tree_receipt


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'fixture', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--repeat', type=int, default=3, choices=range(1, 9))
    args = parser.parse_args()
    system, fixture, out = (p.resolve() for p in (args.system, args.fixture, args.output))
    out.relative_to(ROOT / 'build'); out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'runs': [], 'scope': 'ordinary native clients and real Files operations',
              'not_run': ['physical_power_loss', 'foreign_architecture', 'SMP_kernel'],
              'runner_sha256': sha(Path(__file__))}
    guest = None
    try:
        manifest = json.loads((system / 'manifest.json').read_bytes())
        receipt = json.loads((fixture / 'receipt.json').read_bytes())

        def verify():
            for path, digest in manifest['sources'].items():
                if sha(ROOT / path) != digest:
                    raise ValueError('system source changed: ' + path)
            for path, artifact in manifest['artifacts'].items():
                if sha(system / path) != artifact['sha256']:
                    raise ValueError('system artifact changed: ' + path)
            if not manifest.get('files_uncertain_probe'):
                raise ValueError('actual post-commit reply-loss profile required')
            if receipt['sources'] != {path: sha(ROOT / path) for path in INPUTS}:
                raise ValueError('fixture sources changed')
            if receipt['status'] != 'built_not_run' or receipt['libc_linked']:
                raise ValueError('wrong native fixture profile')
            if tree_receipt(system / 'sdk')[0] != receipt['sdk_tree_sha256']:
                raise ValueError('native SDK changed')
            for path, digest in receipt['artifacts'].items():
                if sha(fixture / path) != digest:
                    raise ValueError('fixture changed')

        verify()
        report.update(build_id=manifest['build_id'], system_manifest_sha256=sha(system / 'manifest.json'),
                      iso_sha256=sha(system / 'xos-install.iso'), fixture_receipt_sha256=sha(fixture / 'receipt.json'),
                      sdk_tree_sha256=receipt['sdk_tree_sha256'], system_sources=manifest['sources'])
        with tempfile.TemporaryDirectory(prefix='xos_p1b_') as temporary:
            disk = Path(temporary) / 'work.img'; create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/budget.elf', fixture / 'budget.elf')
            data = Path(temporary) / 'data.bin'; data.write_bytes(b'P1B invalid manifest for real error-cleanup CLOSE\n')
            for name in ('p1b_good.bin', 'p1b_unknown_open.bin', 'p1b_unknown_close.bin'):
                transfer(disk, 'import', '/' + name, data)
            guest = Guest(system / 'xos-install.iso', 'guest', iso=True, work_disk=disk,
                          qmp_enabled=False, log_dir=out)
            report['qemu_command'] = guest.command
            guest.expect(b'xos64> ', timeout=60); send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, 'demo quiet', b'demo tasks'); command(guest, 'audio stop', b'xsh> ')
            pump(guest, 0.2); baseline = resources(guest); report['baseline'] = baseline

            def stable():
                for _ in range(30):
                    actual = resources(guest)
                    if actual == baseline: return actual
                    pump(guest, 0.1)
                raise AssertionError(f'resource leak {actual}, baseline {baseline}')

            for round_number in range(args.repeat):
                for mode in ('family', 'pages', 'ipc', 'alias', 'exec', 'fresh'):
                    output = command(guest, 'exec-driver /bin/budget.elf ' + mode, b'kind=exited code=', timeout=60)
                    if ('P1B_PASS ' + mode).encode() not in output or b'P1B_FAIL' in output or not re.search(rb'kind=exited code=0', output):
                        raise AssertionError(output[-8000:])
                    report['runs'].append({'round': round_number, 'case': mode, 'status': 'passed', 'resources': stable()})
                for mode in ('unknown_open', 'unknown_close', 'concurrent'):
                    began = len(guest.output)
                    command(guest, 'spawn-file /bin/budget.elf ' + mode, b'xsh> ', timeout=60)
                    guest.expect(b'P1B_QUARANTINED pid=', start=began, timeout=15)
                    pump(guest, 0.1)
                    segment = bytes(guest.output)[began:]
                    found = re.search(rb'P1B_QUARANTINED pid=(\d+) op=(\d+)', segment)
                    if not found: raise AssertionError(segment[-8000:])
                    pid = found[1].decode()
                    # A separate, authenticated process stays usable while the
                    # failed controller still exists and retains quarantine.
                    fresh = command(guest, 'exec-driver /bin/budget.elf fresh', b'kind=exited code=', timeout=30)
                    if b'P1B_PASS fresh' not in fresh or b'P1B_PASS ' + mode.encode() in fresh:
                        raise AssertionError('unrelated owner did not finish while quarantine owner remained alive')
                    command(guest, 'wait ' + pid, b'kind=exited code=', timeout=30)
                    segment = bytes(guest.output)[began:]
                    attempts = re.findall(rb'P1B_FILES_ATTEMPT pid=' + pid.encode() + rb' op=(\d+) request=(\d+) count=(\d+) committed=(\d+)', segment)
                    expected_op = b'8' if mode == 'unknown_close' else b'4'
                    if len(attempts) != 1 or attempts[0][0] != expected_op or attempts[0][2:] != (b'1', b'1'):
                        raise AssertionError('side effect replay or injection was not after commit: ' + repr(attempts))
                    if b'P1B_FAIL' in segment or ('P1B_PASS ' + mode).encode() not in segment:
                        raise AssertionError(segment[-8000:])
                    report['runs'].append({'round': round_number, 'case': mode, 'status': 'passed',
                                           'lost_reply_after_commit': True, 'request_id': int(attempts[0][1]),
                                           'side_effect_attempts': 1, 'unrelated_owner_usable': True, 'resources': stable()})
            verify(); report['status'] = 'passed'
    except BaseException as error:
        report['error'] = str(error); raise
    finally:
        if guest: guest.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS P1-B guest:', len(report['runs']), 'cases with actual resource reclamation')


if __name__ == '__main__':
    main()
