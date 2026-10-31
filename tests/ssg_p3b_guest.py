#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the dual-provider supervisor with synthetic guest-only inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from work_disk import transfer


def fixture():
    return 'A' * 511 + '😀\n' + ''.join(f'{i:04d} Alpha 😀 Omega\n' for i in range(180))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(guest, code):
    for down in (True, False):
        guest.qmp('input-send-event', {'events': [{'type': 'key', 'data': {
            'down': down, 'key': {'type': 'qcode', 'data': code}}}]})
        pump(guest, .1)


def chord(guest, code):
    guest.qmp('input-send-event', {'events': [{'type': 'key', 'data': {
        'down': True, 'key': {'type': 'qcode', 'data': 'ctrl'}}}]})
    pump(guest, .1)
    key(guest, code)
    guest.qmp('input-send-event', {'events': [{'type': 'key', 'data': {
        'down': False, 'key': {'type': 'qcode', 'data': 'ctrl'}}}]})
    pump(guest, .1)


def click(guest, x, y):
    for _ in range(10):
        guest.qmp('input-send-event', {'events': [
            {'type': 'rel', 'data': {'axis': 'x', 'value': -100}},
            {'type': 'rel', 'data': {'axis': 'y', 'value': -100}}]})
        pump(guest, .02)
    for offset in range(0, max(x, y), 80):
        guest.qmp('input-send-event', {'events': [
            {'type': 'rel', 'data': {'axis': 'x', 'value': min(80, max(0, x-offset))}},
            {'type': 'rel', 'data': {'axis': 'y', 'value': min(80, max(0, y-offset))}}]})
        pump(guest, .02)
    for down in (True, False):
        guest.qmp('input-send-event', {'events': [
            {'type': 'btn', 'data': {'button': 'left', 'down': down}}]})
        pump(guest, .1)
def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('image', 'supervisor', 'browser', 'notes', 'input', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--notes-denied', action='store_true')
    p.add_argument('--browser-denied', action='store_true')
    p.add_argument('--ordinary', action='store_true', help='exercise non-diagnostic supervisor and Notes with explicit aggregate output')
    p.add_argument('--case', choices=('baseline', 'edit', 'revoke', 'protect-document', 'protect-ancestor', 'notes-exit', 'browser-exit'), default='baseline')
    a = p.parse_args()
    out = a.output.resolve()
    relative = out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'FAILED', 'case': 'notes-denied' if a.notes_denied else 'browser-denied' if a.browser_denied else 'ordinary' if a.ordinary else a.case,
              'inputs': {name: {'sha256': sha(getattr(a, name))}
                         for name in ('image', 'supervisor', 'browser', 'notes', 'input')},
              'events': [], 'qmp_events': []}
    note = out / 'synthetic-input.txt'
    note.write_text(fixture(), encoding='utf-8')
    report['synthetic_input_sha256'] = sha(note)
    report['synthetic_input_utf16_units'] = len(fixture().encode('utf-16-le')) // 2
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_p3b_') as temp:
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
                report['qmp_events'].append({'command': name, 'arguments': arguments,
                                             'serial_offset': len(guest.output)})
                return original_qmp(name, arguments)
            guest.qmp = record_qmp
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=45)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=45)
            command(guest, 'demo quiet', b'demo tasks stopped')
            report['before_display'] = resources(guest)
            command(guest, 'display-start', b'result=0')
            guest.expect(b'[display-service] ready')
            report['active_display'] = resources(guest)
            start = len(guest.output)
            mode = (' --notes-hidden --emit-aggregate' if a.ordinary else ' --notes-denied' if a.notes_denied else
                    ' --browser-denied' if a.browser_denied else (' --test-' + a.case if a.case != 'baseline' else ''))
            send_bytes(guest, ('exec-driver /bin/multi.elf /web/ssg.html /synthetic.txt' + mode + '\r').encode())
            guest.expect(b'P3B_BOTH_STARTED', start=start, timeout=150)
            if a.case != 'baseline':
                marker = b'P3B_BROWSER_EXIT_READY' if a.case == 'browser-exit' else b'P3B_EDIT_INJECTION_READY'
                guest.expect(marker, start=start, timeout=300)
                injection = {'edit': ('z', b'EDITOR_CHANGE'), 'revoke': ('6', b'SSG_TEST_OWNER_REVOKED'),
                             'protect-document': ('7', b'SSG_TEST_OWNER_DOCUMENT_PROTECTED'),
                             'protect-ancestor': ('8', b'SSG_TEST_OWNER_ANCESTOR_PROTECTED'),
                             'notes-exit': ('esc', None), 'browser-exit': ('esc', None)}
                code, marker = injection[a.case]
                if a.case in ('edit', 'notes-exit', 'browser-exit'):
                    key(guest, code)
                else:
                    chord(guest, code)
                if marker:
                    guest.expect(marker, start=start, timeout=20)
                report['events'].append('real_ps2_' + a.case)
            guest.expect(b'P3B_CAPTURE_COMPLETE', start=start, timeout=360)
            report['events'].append('capture_complete')
            # The edited Notes document must use its real unsaved-change guard.
            if a.case not in ('notes-exit', 'browser-exit'):
                key(guest, 'esc')
            if a.case == 'edit':
                guest.expect(b'EDITOR_UNSAVED_GUARD', start=start, timeout=10)
                guest.expect(b'EDITOR_POINT discard=', start=start, timeout=10)
                match = list(re.finditer(rb'EDITOR_POINT discard=(\d+),(\d+)', bytes(guest.output)[start:]))[-1]
                click(guest, int(match[1]), int(match[2]))
                report['events'].append('real_ps2_discard_unsaved')
            guest.expect(b'P3B_SOURCE_EXIT slot=notes', start=start, timeout=45)
            guest.expect_supervisor(start=start, timeout=45)
            report['after'] = resources(guest)
            output = bytes(guest.output)[start:]
            identities = re.search(rb'P3B_BOTH_STARTED supervisor=(\d+) browser=(\d+) notes=(\d+)', output)
            if not identities or len(set(identities.groups())) != 3:
                raise AssertionError('missing distinct process identities')
            report['processes'] = dict(zip(('supervisor', 'browser', 'notes'), map(int, identities.groups())))
            report['source_exits'] = [line.decode() for line in output.splitlines() if line.startswith(b'P3B_SOURCE_EXIT ')]
            report['aggregate'] = next((line.decode() for line in output.splitlines() if line.startswith(b'P3B_AGGREGATE ')), None)
            report['resources_restored'] = report['active_display'] == report['after']
            if b'P3B_AGGREGATE status=AGGREGATE_COMPLETE_OBSERVED browser=1 notes=1' in output and not a.notes_denied and not a.browser_denied:
                if a.case == 'edit' and b'P3B_DIFF browser=UNCHANGED notes=CHANGED' not in output:
                    raise AssertionError('cross-app edit was not isolated')
                if a.case in ('revoke', 'protect-document', 'protect-ancestor'):
                    wanted = b'DENIED' if a.case == 'revoke' else b'PROTECTED'
                    if b'P3B_DIFF browser=UNCHANGED notes=' + wanted + b' retry_refused=1' not in output:
                        raise AssertionError('restriction or independent browser refresh failed')
                if a.case == 'notes-exit' and b'P3B_DIFF browser=UNCHANGED notes=EXITED' not in output:
                    raise AssertionError('Notes exit was not isolated')
                if a.case == 'browser-exit' and b'P3B_DIFF browser=EXITED notes=UNCHANGED' not in output:
                    raise AssertionError('Browser exit was not isolated')
                report['status'] = 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION'
            elif b'P3B_AGGREGATE status=AGGREGATE_PARTIAL browser=1 notes=0' in output and a.notes_denied:
                report['status'] = 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION'
            elif b'P3B_AGGREGATE status=AGGREGATE_PARTIAL browser=0 notes=1' in output and a.browser_denied and b'P3B_BROWSER_DENIAL_RECHECK refused=1 notes_alive=1' in output:
                report['status'] = 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION'
            else:
                raise AssertionError('aggregate did not have expected status')
    except Exception as exc:
        report['error'] = repr(exc)
        report['traceback'] = traceback.format_exc()
    finally:
        if guest is not None:
            (out / 'serial.log').write_bytes(guest.output)
            guest.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], report.get('error', ''), flush=True)
    return 0 if report['status'] == 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION' else 1


if __name__ == '__main__':
    raise SystemExit(main())
