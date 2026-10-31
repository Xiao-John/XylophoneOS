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
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from ssg_public_paths import portable
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
    p.add_argument('--default-denied', action='store_true', help='grant neither source text access')
    p.add_argument('--ordinary-default-denied', action='store_true', help='check default denial in the ordinary build')
    p.add_argument('--ordinary', action='store_true', help='exercise non-diagnostic supervisor and Notes with explicit aggregate output')
    p.add_argument('--ordinary-sample', action='store_true', help='exercise two ordinary observations and their per-source Diff')
    p.add_argument('--old-instance', help='test a source instance captured from an earlier session')
    p.add_argument('--case', choices=('baseline', 'edit', 'revoke', 'protect-document', 'protect-ancestor', 'browser-revoke', 'browser-reload', 'browser-scroll', 'pipe-isolation', 'notes-exit', 'browser-exit', 'browser-exit-during-notes', 'notes-timeout', 'notes-truncated', 'notes-cancel'), default='baseline')
    a = p.parse_args()
    started = time.monotonic()
    out = a.output.resolve()
    relative = out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'FAILED', 'case': 'default-denied' if a.default_denied or a.ordinary_default_denied else 'notes-denied' if a.notes_denied else 'browser-denied' if a.browser_denied else 'ordinary-sample' if a.ordinary_sample else 'ordinary' if a.ordinary else 'old-instance' if a.old_instance else a.case,
              'inputs': {name: {'sha256': sha(getattr(a, name))}
                         for name in ('image', 'supervisor', 'browser', 'notes', 'input')},
              'events': [], 'qmp_events': []}
    report['ordinary_default_denied'] = a.ordinary_default_denied
    report['runner_sha256'] = sha(ROOT / 'tests/ssg_p3b_guest.py')
    browser_receipt = a.browser.with_suffix('.portable.receipt.json')
    if browser_receipt.is_file():
        (out / 'browser.receipt.json').write_bytes(browser_receipt.read_bytes())
        report['browser_receipt_sha256'] = sha(browser_receipt)
    if a.old_instance:
        if not re.fullmatch(r'[0-9a-f]{32}', a.old_instance):
            p.error('old instance must be 32 lowercase hexadecimal characters')
        report['old_instance'] = a.old_instance
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
            report['qemu_sha256'] = sha(Path(guest.command[0]))
            report['qemu_command_template'] = portable(guest.command, [
                ('XOS_IMAGE', a.image), ('XOS_QEMU', guest.command[0]), ('XOS_WORK_DISK', disk),
                ('XOS_QMP_SOCKET', guest.qmp_path)], strict=True)
            guest.expect(b'xos64> ', timeout=45)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=45)
            command(guest, 'demo quiet', b'demo tasks stopped')
            report['before_display'] = resources(guest)
            command(guest, 'display-start', b'result=0')
            guest.expect(b'[display-service] ready')
            report['active_display'] = resources(guest)
            start = len(guest.output)
            mode = (' --notes-hidden --emit-aggregate --sample-twice --sample-interval 1' if a.ordinary_sample else
                    ' --notes-hidden --emit-aggregate' if a.ordinary_default_denied else
                    ' --notes-hidden --emit-aggregate' if a.ordinary else ' --notes-denied' if a.notes_denied else
                    ' --browser-denied' if a.browser_denied else (' --old-instance ' + a.old_instance) if a.old_instance else
                    (' --test-' + a.case if a.case != 'baseline' else ''))
            if not (a.default_denied or a.ordinary_default_denied):
                if not a.browser_denied: mode += ' --browser-text'
                if not a.notes_denied: mode += ' --notes-text'
            send_bytes(guest, ('exec-driver /bin/multi.elf /web/ssg.html /synthetic.txt' + mode + '\r').encode())
            guest.expect(b'P3B_BOTH_STARTED', start=start, timeout=150)
            if a.case not in ('baseline', 'notes-timeout', 'notes-truncated', 'notes-cancel', 'pipe-isolation'):
                marker = (b'P3B_BROWSER_EXIT_READY' if a.case == 'browser-exit' else
                          b'P3B_BROWSER_REVOKE_READY' if a.case == 'browser-revoke' else
                          b'P3B_BROWSER_SCROLL_READY' if a.case == 'browser-scroll' else
                          b'P3B_BROWSER_RELOAD_READY' if a.case == 'browser-reload' else b'P3B_EDIT_INJECTION_READY')
                reached = guest.expect_any((marker, b'P3B_CAPTURE_COMPLETE'), start=start, timeout=300)
                if reached != marker:
                    raise AssertionError('collection ended before input injection point')
                injection = {'edit': ('z', b'EDITOR_CHANGE'), 'revoke': ('6', b'SSG_TEST_OWNER_REVOKED'),
                             'protect-document': ('7', b'SSG_TEST_OWNER_DOCUMENT_PROTECTED'),
                             'protect-ancestor': ('8', b'SSG_TEST_OWNER_ANCESTOR_PROTECTED'),
                             'notes-exit': ('esc', None), 'browser-exit': ('esc', None),
                             'browser-exit-during-notes': ('esc', None),
                             'browser-revoke': ('9', b'SSG_TEST_BROWSER_REVOKED'),
                             'browser-reload': ('r', b'BROWSER_LOADED path='),
                             'browser-scroll': ('pgdn', b'BROWSER_SCROLL value=')}
                code, marker = injection[a.case]
                input_start = len(guest.output)
                if a.case in ('edit', 'notes-exit', 'browser-exit', 'browser-exit-during-notes', 'browser-scroll'):
                    key(guest, code)
                else:
                    chord(guest, code)
                if marker:
                    guest.expect(marker, start=input_start, timeout=20)
                report['events'].append('real_ps2_' + a.case)
            guest.expect(b'P3B_CAPTURE_COMPLETE', start=start, timeout=360)
            report['events'].append('capture_complete')
            # The edited Notes document must use its real unsaved-change guard.
            if a.case not in ('notes-exit', 'browser-exit', 'browser-exit-during-notes'):
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
            wait = re.search(rb'\[wait\] pid=' + str(report['processes']['supervisor']).encode() + rb' kind=(\w+) code=(-?\d+)', output)
            report['supervisor_exit'] = {'kind': wait[1].decode(), 'code': int(wait[2])} if wait else None
            report['thread_samples'] = [line.decode() for line in output.splitlines()
                                        if line.startswith((b'EDITOR_SAMPLE ', b'BROWSER_SAMPLE '))]
            report['pipe_capacity_probe'] = next((line.decode() for line in output.splitlines()
                                                  if line.startswith(b'P3B_PIPE_REUSE ')), 'NOT_AVAILABLE')
            shutdown = re.search(rb'P3B_SHUTDOWN elapsed_ns=(\d+) clean=([01])', output)
            report['shutdown'] = {'elapsed_ns': int(shutdown[1]), 'clean': shutdown[2] == b'1'} if shutdown else None
            report['aggregate'] = next((line.decode() for line in output.splitlines() if line.startswith(b'P3B_AGGREGATE ')), None)
            report['resources_restored'] = report['active_display'] == report['after']
            expected_code = 1 if a.notes_denied or a.default_denied or a.ordinary_default_denied else 0
            if report['supervisor_exit'] != {'kind': 'exited', 'code': expected_code}:
                raise AssertionError('supervisor exit was not the expected result')
            if b'P3B_AGGREGATE status=AGGREGATE_COMPLETE_OBSERVED browser=1 notes=1' in output and not a.notes_denied and not a.browser_denied and not a.default_denied and not a.ordinary_default_denied:
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
                if a.case == 'browser-exit-during-notes' and b'P3B_CROSS_EXIT browser=UNAVAILABLE notes=OBSERVED_COMPLETE' not in output:
                    raise AssertionError('source death during the other read was not isolated')
                if a.case == 'browser-revoke' and b'P3B_DIFF browser=DENIED notes=UNCHANGED retry_refused=1' not in output:
                    raise AssertionError('Browser revocation was not isolated')
                if a.case == 'browser-reload' and b'P3B_DIFF browser=REPLACED notes=UNCHANGED old_reference=SOURCE_REPLACED' not in output:
                    raise AssertionError('Browser document replacement was not isolated')
                if a.case == 'browser-scroll' and not re.search(rb'P3B_SCROLL before=\d+ after=[1-9]\d* scroll=1 .* notes=UNCHANGED', output):
                    raise AssertionError('Browser scroll was not isolated')
                if a.case == 'pipe-isolation' and b'P3B_PIPE_CROSS_DENIAL browser=1 notes=1 browser_after=1 notes_after=1' not in output:
                    raise AssertionError('cross-source token isolation failed')
                if a.old_instance and b'P3B_OLD_INSTANCE status=SOURCE_REPLACED' not in output:
                    raise AssertionError('old source instance was not refused')
                if a.case in ('notes-timeout', 'notes-truncated', 'notes-cancel'):
                    failure = b'TIMEOUT' if a.case == 'notes-timeout' else b'TRUNCATED' if a.case == 'notes-truncated' else b'CANCELLED'
                    provider_fault = b'CANCEL_STALL' if a.case == 'notes-cancel' else failure
                    if b'SSG_TEST_PROVIDER_FAULT kind=' + provider_fault not in output or b'P3B_DIFF browser=UNCHANGED notes=' + failure not in output:
                        raise AssertionError('injected transport fault was not isolated')
                report['status'] = 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION'
            elif b'P3B_AGGREGATE status=AGGREGATE_PARTIAL browser=1 notes=0' in output and a.notes_denied:
                report['status'] = 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION'
            elif b'P3B_AGGREGATE status=AGGREGATE_PARTIAL browser=0 notes=1' in output and a.browser_denied and b'P3B_BROWSER_DENIAL_RECHECK refused=1 notes_alive=1' in output:
                report['status'] = 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION'
            elif b'P3B_AGGREGATE status=AGGREGATE_PARTIAL browser=0 notes=0' in output and (a.default_denied or a.ordinary_default_denied):
                report['status'] = 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION'
            else:
                raise AssertionError('aggregate did not have expected status')
    except Exception as exc:
        report['error'] = repr(exc)
        report['traceback'] = traceback.format_exc()
    finally:
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        if guest is not None:
            (out / 'serial.log').write_bytes(guest.output)
            guest.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], report.get('error', ''), flush=True)
    return 0 if report['status'] == 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION' else 1


if __name__ == '__main__':
    raise SystemExit(main())
