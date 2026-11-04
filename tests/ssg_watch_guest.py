#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise real PS/2 input against the existing two-provider guest session."""
import argparse
import hashlib
import json
from pathlib import Path
import re
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
from ssg_p3b_guest import fixture, key, chord, click
from ssg_public_paths import portable
from task_smoke import send_bytes
from work_disk import transfer


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('image', 'supervisor', 'browser', 'notes', 'input', 'browser-receipt', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--case', choices=('baseline', 'stop', 'cancel-inflight', 'cap-retry', 'cap-persistent', 'edit', 'scroll', 'reload', 'revoke',
                                     'protect-document', 'protect-ancestor', 'browser-exit', 'notes-exit', 'notes-timeout'), default='baseline')
    p.add_argument('--ordinary', action='store_true', help='use the non-diagnostic programs for the baseline case')
    a = p.parse_args()
    if a.ordinary and a.case != 'baseline':
        p.error('ordinary mode only supports the baseline case')
    started = time.monotonic()
    out = a.output.resolve()
    relative = out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'FAILED', 'case': a.case, 'ordinary': a.ordinary, 'events': [], 'qmp_events': [],
              'inputs': {name: {'sha256': sha(getattr(a, name))} for name in ('image', 'supervisor', 'browser', 'notes', 'input')}}
    (out / 'browser.receipt.json').write_bytes(a.browser_receipt.read_bytes())
    note = out / 'synthetic-input.txt'
    note.write_text(fixture(), encoding='utf-8')
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_p3c_') as temp:
            disk = Path(temp) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'mkdir', '/web')
            for source, dest in ((a.supervisor, 'multi'), (a.browser, 'browser'), (a.notes, 'notes')):
                transfer(disk, 'import', '/bin/' + dest + '.elf', source)
            transfer(disk, 'import', '/web/ssg.html', a.input)
            transfer(disk, 'import', '/synthetic.txt', note)
            guest = Guest(a.image.resolve(), str(relative) + '/guest', work_disk=disk)
            original_qmp = guest.qmp
            def record_qmp(name, arguments=None):
                report['qmp_events'].append({'command': name, 'arguments': arguments, 'serial_offset': len(guest.output)})
                return original_qmp(name, arguments)
            guest.qmp = record_qmp
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            report['qemu_sha256'] = sha(Path(guest.command[0]))
            report['qemu_command_template'] = portable(guest.command, [('XOS_IMAGE', a.image), ('XOS_QEMU', guest.command[0]),
                ('XOS_WORK_DISK', disk), ('XOS_QMP_SOCKET', guest.qmp_path)], strict=True)
            guest.expect(b'xos64> ', timeout=45)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=45)
            command(guest, 'demo quiet', b'demo tasks stopped')
            command(guest, 'display-start', b'result=0')
            guest.expect(b'[display-service] ready')
            report['active_display'] = resources(guest)
            start = len(guest.output)
            browser_visible = a.case in ('baseline', 'stop', 'cancel-inflight', 'cap-retry', 'cap-persistent', 'scroll', 'reload', 'browser-exit', 'notes-timeout')
            mode = ('--test-watch-cancel' if a.case == 'cancel-inflight' else '--test-watch-capped' if a.case == 'cap-retry' else
                    '--test-watch-capped-always' if a.case == 'cap-persistent' else '--test-notes-timeout' if a.case == 'notes-timeout' else
                    '--test-watch-browser' if browser_visible else '--test-watch-notes')
            if a.ordinary:
                mode = '--notes-hidden'
            cmd = ('exec-driver /bin/multi.elf /web/ssg.html /synthetic.txt ' + mode +
                   ' --browser-text --notes-text --watch --watch-cycles 3 --watch-interval 4 --watch-duration 240 --watch-timeout 60\r')
            if a.case == 'stop':
                cmd = cmd[:-1] + ' --test-watch-stop-control\r'
            send_bytes(guest, cmd.encode())
            guest.expect(b'P3B_BOTH_STARTED', start=start, timeout=150)
            actions = {
                'edit': [('z', False, b'EDITOR_CHANGE'), ('x', False, b'EDITOR_CHANGE')],
                'scroll': [('pgdn', False, b'BROWSER_SCROLL value='), ('pgdn', False, b'BROWSER_SCROLL value=')],
                'reload': [('r', True, b'BROWSER_LOADED path=')],
                'revoke': [('6', True, b'SSG_TEST_OWNER_REVOKED')],
                'protect-document': [('7', True, b'SSG_TEST_OWNER_DOCUMENT_PROTECTED')],
                'protect-ancestor': [('8', True, b'SSG_TEST_OWNER_ANCESTOR_PROTECTED')],
                'browser-exit': [('esc', False, None)], 'notes-exit': [('esc', False, None)],
            }.get(a.case, [])
            for index, (code, ctrl, marker) in enumerate(actions, 1):
                ready = ('P3C_CYCLE_READY cycle=%d ' % index).encode()
                guest.expect(ready, start=start, timeout=300)
                offset = len(guest.output)
                (chord if ctrl else key)(guest, code)
                if marker:
                    guest.expect(marker, start=offset, timeout=30)
                report['events'].append({'cycle': index, 'key': code, 'ctrl': ctrl, 'serial_offset': offset})
            guest.expect(b'P3B_CAPTURE_COMPLETE', start=start, timeout=480)
            if a.case not in ('browser-exit', 'notes-exit'):
                key(guest, 'esc')
            if a.case == 'edit':
                guest.expect(b'EDITOR_UNSAVED_GUARD', start=start, timeout=15)
                guest.expect(b'EDITOR_POINT discard=', start=start, timeout=15)
                match = list(re.finditer(rb'EDITOR_POINT discard=(\d+),(\d+)', bytes(guest.output)[start:]))[-1]
                click(guest, int(match[1]), int(match[2]))
                report['discarded_unsaved_synthetic_edit'] = True
            guest.expect(b'P3B_SOURCE_EXIT slot=notes', start=start, timeout=60)
            guest.expect_supervisor(start=start, timeout=60)
            report['after'] = resources(guest)
            output = bytes(guest.output)[start:]
            ids = re.search(rb'P3B_BOTH_STARTED supervisor=(\d+) browser=(\d+) notes=(\d+)', output)
            if not ids or len(set(ids.groups())) != 3:
                raise AssertionError('missing distinct process identities')
            report['processes'] = dict(zip(('supervisor', 'browser', 'notes'), map(int, ids.groups())))
            report['source_exits'] = [line.decode() for line in output.splitlines() if line.startswith(b'P3B_SOURCE_EXIT ')]
            wait = re.search(rb'\[wait\] pid=' + str(report['processes']['supervisor']).encode() + rb' kind=(\w+) code=(-?\d+)', output)
            report['supervisor_exit'] = {'kind': wait[1].decode(), 'code': int(wait[2])} if wait else None
            report['thread_samples'] = [line.decode() for line in output.splitlines() if line.startswith((b'EDITOR_SAMPLE ', b'BROWSER_SAMPLE '))]
            report['resources_restored'] = report['active_display'] == report['after']
            if report['supervisor_exit'] != {'kind': 'exited', 'code': 0} or not report['resources_restored']:
                raise AssertionError('supervisor exit or resource recovery failed')
            expected_stop = (b'P3C_WATCH_STOP reason=EXPLICIT_STOP cycles=1 events=2 dropped=0' if a.case == 'cancel-inflight' else
                             b'P3C_WATCH_STOP reason=EXPLICIT_STOP cycles=2 events=4 dropped=0' if a.case == 'stop' else
                             b'P3C_WATCH_STOP reason=CYCLE_LIMIT cycles=3 events=6 dropped=0')
            if expected_stop not in output:
                raise AssertionError('watch did not finish at the expected stop')
            report['status'] = 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION'
    except Exception as exc:
        report['error'] = repr(exc)
        report['traceback'] = traceback.format_exc()
    finally:
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        if guest:
            (out / 'serial.log').write_bytes(guest.output)
            guest.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], report.get('error', ''), flush=True)
    return 0 if report['status'] == 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION' else 1


if __name__ == '__main__':
    raise SystemExit(main())
