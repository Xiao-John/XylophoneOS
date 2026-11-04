#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Repeat complete dual-provider sessions inside a single XOS boot."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from ssg_p3b_guest import fixture, key
from ssg_public_paths import portable
from task_smoke import send_bytes
from work_disk import transfer


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('image', 'supervisor', 'browser', 'notes', 'input', 'browser-receipt', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--count', type=int, default=32)
    a = p.parse_args()
    if not 1 <= a.count <= 64:
        p.error('count must be 1–64')
    out = a.output.resolve()
    relative = out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    inputs = {name: {'sha256': sha(getattr(a, name))} for name in ('image', 'supervisor', 'browser', 'notes', 'input')}
    summary = {'status': 'RUNNING', 'scope': 'sequential complete synthetic sessions in one XOS boot',
               'target': a.count, 'runs': [], 'inputs': inputs,
               'runner_sha256': sha(Path(__file__)), 'verifier_sha256': sha(ROOT / 'tests/ssg_p3b_verify.py'),
               'pipe_counter': 'UNAVAILABLE; four-pipe capacity probe is not an exact global counter'}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_p3b_stress_') as temp:
            disk = Path(temp) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'mkdir', '/web')
            for source, dest in ((a.supervisor, 'multi'), (a.browser, 'browser'), (a.notes, 'notes')):
                transfer(disk, 'import', '/bin/' + dest + '.elf', source)
            transfer(disk, 'import', '/web/ssg.html', a.input)
            note = Path(temp) / 'synthetic.txt'
            note.write_text(fixture(), encoding='utf-8')
            transfer(disk, 'import', '/synthetic.txt', note)
            guest = Guest(a.image.resolve(), str(relative) + '/guest', work_disk=disk)
            summary['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            summary['qemu_sha256'] = sha(Path(guest.command[0]))
            summary['qemu_command_template'] = portable(guest.command, [
                ('XOS_IMAGE', a.image), ('XOS_QEMU', guest.command[0]), ('XOS_WORK_DISK', disk),
                ('XOS_QMP_SOCKET', guest.qmp_path)], strict=True)
            guest.expect(b'xos64> ', timeout=45)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=45)
            command(guest, 'demo quiet', b'demo tasks stopped')
            command(guest, 'display-start', b'result=0')
            guest.expect(b'[display-service] ready')
            active = resources(guest)
            summary['active_display_resources'] = active
            consecutive_failures = 0
            for i in range(1, a.count + 1):
                case_dir = out / f'run-{i:02d}'
                case_dir.mkdir()
                (case_dir / 'synthetic-input.txt').write_text(fixture(), encoding='utf-8')
                (case_dir / 'browser.receipt.json').write_bytes(a.browser_receipt.read_bytes())
                start = len(guest.output)
                started = time.monotonic()
                item = {'run': i, 'status': 'FAILED', 'timeout': False}
                try:
                    send_bytes(guest, b'exec-driver /bin/multi.elf /web/ssg.html /synthetic.txt --browser-text --notes-text\r')
                    guest.expect(b'P3B_BOTH_STARTED', start=start, timeout=150)
                    guest.expect(b'P3B_CAPTURE_COMPLETE', start=start, timeout=360)
                    key(guest, 'esc')
                    guest.expect(b'P3B_SOURCE_EXIT slot=notes', start=start, timeout=60)
                    guest.expect_supervisor(start=start, timeout=60)
                    output = bytes(guest.output)[start:]
                    after = resources(guest)
                    match = re.search(rb'P3B_BOTH_STARTED supervisor=(\d+) browser=(\d+) notes=(\d+)', output)
                    if not match:
                        raise AssertionError('missing process identities')
                    pids = dict(zip(('supervisor', 'browser', 'notes'), map(int, match.groups())))
                    exits = [line.decode() for line in output.splitlines() if line.startswith(b'P3B_SOURCE_EXIT ')]
                    wait = re.search(rb'\[wait\] pid=' + str(pids['supervisor']).encode() + rb' kind=(\w+) code=(-?\d+)', output)
                    shutdown = re.search(rb'P3B_SHUTDOWN elapsed_ns=(\d+) clean=([01])', output)
                    probe = next((line.decode() for line in output.splitlines() if line.startswith(b'P3B_PIPE_REUSE ')), None)
                    stale = next((line.decode() for line in output.splitlines() if line.startswith(b'P3B_STALE_TOKEN_REFUSED ')), None)
                    reclaimed = [int(x) for x in re.findall(rb'\[task\] event=reclaimed pid=(\d+)', output)]
                    reclaim_order = [slot for pid in reclaimed for slot in ('browser', 'notes') if pid == pids[slot]]
                    supervisor_exit = {'kind': wait[1].decode(), 'code': int(wait[2])} if wait else None
                    case = {'status': 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION', 'case': 'baseline', 'processes': pids,
                            'supervisor_exit': supervisor_exit,
                            'inputs': inputs, 'resources_restored': active == after, 'source_exits': exits}
                    (case_dir / 'serial.log').write_bytes(output)
                    (case_dir / 'report.json').write_text(json.dumps(case, indent=2) + '\n')
                    with (case_dir / 'verify.log').open('wb') as log:
                        verified = subprocess.run([sys.executable, str(ROOT / 'tests/ssg_p3b_verify.py'), str(case_dir),
                                                   '--browser-receipt', str(a.browser_receipt)], cwd=ROOT,
                                                  stdout=log, stderr=subprocess.STDOUT).returncode == 0
                    clean_exits = len(exits) == 2 and all('reaped=1 cancelled=0 outcome=1 code=0' in line for line in exits)
                    samples = [line.decode() for line in output.splitlines() if line.startswith((b'EDITOR_SAMPLE ', b'BROWSER_SAMPLE '))]
                    has_thread_samples = any(x.startswith('EDITOR_SAMPLE ') for x in samples) and any(x.startswith('BROWSER_SAMPLE ') for x in samples)
                    shutdown_result = {'elapsed_ns': int(shutdown[1]), 'clean': shutdown[2] == b'1'} if shutdown else None
                    good = (verified and active == after and clean_exits and has_thread_samples and
                            supervisor_exit == {'kind': 'exited', 'code': 0} and shutdown_result is not None and shutdown_result['clean'] and
                            probe == 'P3B_PIPE_REUSE acquired=4 requested=4' and
                            stale == 'P3B_STALE_TOKEN_REFUSED checked=4 denied=4 reused=0' and sorted(reclaim_order) == ['browser', 'notes'])
                    item.update(status='PASSED' if good else 'FAILED', processes=pids, supervisor_exit=supervisor_exit,
                                source_exits=exits, before_resources=active, after_resources=after, shutdown=shutdown_result,
                                pipe_capacity_probe=probe, stale_token_probe=stale, reclaim_order=reclaim_order,
                                independent_check='PASSED' if verified else 'FAILED',
                                thread_samples=samples)
                    consecutive_failures = 0 if good else consecutive_failures + 1
                except Exception as error:
                    item['error_type'] = type(error).__name__
                    item['error'] = str(error)
                    item['timeout'] = 'missing any of' in str(error)
                    (case_dir / 'serial.log').write_bytes(bytes(guest.output)[start:])
                    summary['stop_reason'] = 'session did not return safely to the shell'
                    consecutive_failures = 3
                item['elapsed_seconds'] = round(time.monotonic() - started, 3)
                summary['runs'].append(item)
                summary['passed'] = sum(v['status'] == 'PASSED' for v in summary['runs'])
                (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
                print(f'run {i}/{a.count}: {item["status"]}, {item["elapsed_seconds"]} s', flush=True)
                if consecutive_failures >= 3:
                    summary.setdefault('stop_reason', 'three consecutive failed runs')
                    break
            summary['status'] = 'PASSED_SCOPED' if len(summary['runs']) == a.count and summary['passed'] == a.count else 'PARTIAL'
    except KeyboardInterrupt:
        summary['status'] = 'PARTIAL'
        summary['stop_reason'] = 'interrupted by operator; completed runs remain recorded'
    except Exception as error:
        summary['status'] = 'PARTIAL'
        summary['error_type'] = type(error).__name__
        summary['error'] = str(error)
    finally:
        if guest:
            (out / 'serial.log').write_bytes(guest.output)
            guest.close()
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(summary['status'], summary.get('passed', 0), '/', a.count, flush=True)
    return 0 if summary['status'] == 'PASSED_SCOPED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
