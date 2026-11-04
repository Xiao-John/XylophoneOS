#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Repeat complete, independently checked two-scroll watch sessions in one boot."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from ssg_p3b_guest import fixture, key
from ssg_public_paths import portable
from ssg_watch_events import decode_event_records
from task_smoke import send_bytes
from work_disk import transfer


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('image', 'supervisor', 'browser', 'notes', 'input', 'browser-receipt', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--count', type=int, default=24)
    a = p.parse_args()
    if not 1 <= a.count <= 64:
        p.error('count must be 1–64')
    out = a.output.resolve()
    relative = out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    inputs = {name: {'sha256': sha(getattr(a, name))} for name in ('image', 'supervisor', 'browser', 'notes', 'input')}
    summary = {'status': 'RUNNING', 'target': a.count, 'runs': [], 'inputs': inputs,
               'latency_scope': 'host wall time from immediately before QMP key injection until next complete-cycle marker; an upper bound including observation and serial capture, not a hard real-time latency',
               'resource_scope': 'sampled free user pages and task counts; not absolute memory peaks or a global pipe counter',
               'runner_sha256': sha(Path(__file__)), 'verifier_sha256': sha(ROOT / 'tests/ssg_watch_verify.py')}
    guest = None
    started_all = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='xos_p3c_stress_') as temp:
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
            summary['qemu_command_template'] = portable(guest.command, [('XOS_IMAGE', a.image), ('XOS_QEMU', guest.command[0]),
                ('XOS_WORK_DISK', disk), ('XOS_QMP_SOCKET', guest.qmp_path)], strict=True)
            guest.expect(b'xos64> ', timeout=45)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=45)
            command(guest, 'demo quiet', b'demo tasks stopped')
            command(guest, 'display-start', b'result=0')
            guest.expect(b'[display-service] ready')
            active = resources(guest)
            summary['active_display_resources'] = active
            original_qmp = guest.qmp
            consecutive_failures = 0
            for index in range(1, a.count + 1):
                case = out / ('run-%02d' % index)
                case.mkdir()
                (case / 'browser.receipt.json').write_bytes(a.browser_receipt.read_bytes())
                (case / 'synthetic-input.txt').write_text(fixture(), encoding='utf-8')
                start = len(guest.output)
                started = time.monotonic()
                report = {'status': 'FAILED', 'case': 'scroll', 'inputs': inputs, 'events': [], 'qmp_events': [], 'active_display': active}
                item = {'run': index, 'status': 'FAILED', 'latency_upper_seconds': [], 'retries': None, 'dropped_events': None}
                def record_qmp(name, arguments=None):
                    report['qmp_events'].append({'command': name, 'arguments': arguments, 'serial_offset': len(guest.output) - start})
                    return original_qmp(name, arguments)
                guest.qmp = record_qmp
                try:
                    send_bytes(guest, b'exec-driver /bin/multi.elf /web/ssg.html /synthetic.txt --test-watch-browser --browser-text --notes-text --watch --watch-cycles 3 --watch-interval 2 --watch-duration 240 --watch-timeout 60\r')
                    guest.expect(b'P3B_BOTH_STARTED', start=start, timeout=150)
                    for cycle in (1, 2):
                        guest.expect(('P3C_CYCLE_READY cycle=%d ' % cycle).encode(), start=start, timeout=300)
                        offset = len(guest.output) - start
                        input_at = time.monotonic()
                        key(guest, 'pgdn')
                        guest.expect(b'BROWSER_SCROLL value=', start=start + offset, timeout=30)
                        report['events'].append({'cycle': cycle, 'key': 'pgdn', 'ctrl': False, 'serial_offset': offset})
                        guest.expect(('P3C_CYCLE_READY cycle=%d ' % (cycle + 1)).encode(), start=start, timeout=300)
                        item['latency_upper_seconds'].append(round(time.monotonic() - input_at, 3))
                    guest.expect(b'P3B_CAPTURE_COMPLETE', start=start, timeout=300)
                    key(guest, 'esc')
                    guest.expect(b'P3B_SOURCE_EXIT slot=notes', start=start, timeout=60)
                    guest.expect_supervisor(start=start, timeout=60)
                    after = resources(guest)
                    output = bytes(guest.output)[start:]
                    ids = re.search(rb'P3B_BOTH_STARTED supervisor=(\d+) browser=(\d+) notes=(\d+)', output)
                    if not ids or len(set(ids.groups())) != 3:
                        raise AssertionError('missing distinct process identities')
                    report['processes'] = dict(zip(('supervisor', 'browser', 'notes'), map(int, ids.groups())))
                    report['source_exits'] = [line.decode() for line in output.splitlines() if line.startswith(b'P3B_SOURCE_EXIT ')]
                    reclaimed = {int(pid): int(pages) for pid, pages in re.findall(rb'\[task\] event=reclaimed pid=(\d+) pages=(\d+)', output)}
                    report['reclaimed_pages'] = {slot: reclaimed.get(pid) for slot, pid in report['processes'].items()}
                    wait = re.search(rb'\[wait\] pid=' + str(report['processes']['supervisor']).encode() + rb' kind=(\w+) code=(-?\d+)', output)
                    report['supervisor_exit'] = {'kind': wait[1].decode(), 'code': int(wait[2])} if wait else None
                    report['thread_samples'] = [line.decode() for line in output.splitlines() if line.startswith((b'EDITOR_SAMPLE ', b'BROWSER_SAMPLE '))]
                    report['after'] = after
                    report['resources_restored'] = active == after
                    if report['supervisor_exit'] != {'kind': 'exited', 'code': 0} or not report['resources_restored']:
                        raise AssertionError('exit or resource restoration')
                    if b'P3C_WATCH_STOP reason=CYCLE_LIMIT cycles=3 events=6 dropped=0' not in output:
                        raise AssertionError('watch did not complete')
                    report['status'] = 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION'
                    report['elapsed_seconds'] = round(time.monotonic() - started, 3)
                    (case / 'serial.log').write_bytes(output)
                    (case / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
                    checked = subprocess.run([sys.executable, str(ROOT / 'tests/ssg_watch_verify.py'), str(case), '--require-structured'],
                                             capture_output=True, text=True)
                    (case / 'verify.log').write_text(checked.stdout + checked.stderr)
                    if checked.returncode:
                        raise AssertionError('independent verifier failed')
                    verified = json.loads((case / 'independent-check.json').read_text())
                    emitted = [record['data'] for record in decode_event_records(output)]
                    dropped = re.search(rb'P3C_WATCH_STOP .* dropped=(\d+)', output)
                    if not dropped:
                        raise AssertionError('drop counter missing')
                    item.update({'status': verified['status'], 'elapsed_seconds': report['elapsed_seconds'],
                                 'observations': len(emitted),
                                 'change_events': sum(event['event_type'] == 'SOURCE_CHANGED' for event in emitted),
                                 'resyncs': sum(event['event_type'] in ('RESET_REQUIRED', 'SOURCE_REPLACED') for event in emitted),
                                 'retries': sum(event.get('retry_count', 0) for event in emitted),
                                 'dropped_events': int(dropped[1]),
                                 'ipc_requests': verified['ipc_requests'], 'ipc_bytes': verified['ipc_bytes_including_frame_headers'],
                                 'source_exits': report['source_exits'], 'resource_samples': report['thread_samples'],
                                 'reclaimed_pages': report['reclaimed_pages'],
                                 'resources_restored': report['resources_restored']})
                except Exception as exc:
                    item['error'] = repr(exc)
                    item['traceback'] = traceback.format_exc()
                    failed_output = bytes(guest.output)[start:]
                    (case / 'serial.log').write_bytes(failed_output)
                    drop_match = re.search(rb'P3C_WATCH_STOP .* dropped=(\d+)', failed_output)
                    if drop_match:item['dropped_events'] = int(drop_match[1])
                    try:
                        partial = [record['data'] for record in decode_event_records(failed_output, require_stop=False)]
                        item['observations'] = len(partial)
                        item['change_events'] = sum(event['event_type'] == 'SOURCE_CHANGED' for event in partial)
                        item['resyncs'] = sum(event['event_type'] in ('RESET_REQUIRED', 'SOURCE_REPLACED') for event in partial)
                        item['retries'] = sum(event.get('retry_count', 0) for event in partial)
                        item['event_counts_scope'] = 'complete decoded records; stream may be incomplete'
                    except (ValueError, json.JSONDecodeError):
                        item['event_counts_scope'] = 'UNKNOWN: malformed or incomplete event records'
                    item['source_exits'] = report.get('source_exits')
                    item['resources_restored'] = report.get('resources_restored')
                    report['elapsed_seconds'] = round(time.monotonic() - started, 3)
                    (case / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
                finally:
                    guest.qmp = original_qmp
                    summary['runs'].append(item)
                    summary['elapsed_seconds'] = round(time.monotonic() - started_all, 3)
                    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
                    print('STRESS run=%d status=%s elapsed=%s' % (index, item['status'], item.get('elapsed_seconds', report['elapsed_seconds'])), flush=True)
                if item['status'] == 'PASSED_SCOPED':
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    # A contained failure with recovered resources remains a
                    # failed run, but need not erase the rest of the sample.
                    # Stop on an unsafe guest state or repeated failures.
                    if not report.get('resources_restored') or consecutive_failures >= 3:
                        break
            if len(summary['runs']) == a.count and all(run['status'] == 'PASSED_SCOPED' for run in summary['runs']):
                summary['status'] = 'PASSED_SCOPED'
            else:
                summary['status'] = 'FAILED'
            summary['passed_runs'] = sum(run['status'] == 'PASSED_SCOPED' for run in summary['runs'])
            summary['failed_runs'] = sum(run['status'] != 'PASSED_SCOPED' for run in summary['runs'])
            latencies = sorted(value for run in summary['runs'] for value in run['latency_upper_seconds'])
            if latencies:
                summary['latency_upper_seconds'] = {'count': len(latencies), 'min': min(latencies), 'median': statistics.median(latencies),
                                                    'p95_nearest_rank': latencies[(95 * len(latencies) + 99) // 100 - 1], 'max': max(latencies)}
    finally:
        summary['elapsed_seconds'] = round(time.monotonic() - started_all, 3)
        if guest:
            guest.close()
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(summary['status'], flush=True)
    return 0 if summary['status'] == 'PASSED_SCOPED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
