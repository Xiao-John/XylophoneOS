#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise a synthetic Notes document through independent QEMU processes.

The owner shortcuts exist only in tests/fixtures/qt6/notes_live_test.cpp. Raw
captures remain in the selected build directory until separately reviewed.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from ssg_public_paths import portable
from task_smoke import send_bytes, pump
from work_disk import transfer


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixture():
    # A surrogate pair straddles the first nominal 512-unit boundary.
    return 'A' * 511 + '😀\n' + ''.join(f'{i:04d} Alpha 😀 Omega\n' for i in range(180))


def frames(output):
    result = {}
    for direction, seq, size, encoded_size in re.findall(
            rb'SSG_FRAME_BEGIN (REQ|RESP|TEXT) (\d+) (\d+) (\d+)', output):
        prefix = rb'SSG_FRAME_PART ' + direction + b' ' + seq + rb' (\d+) ([A-Za-z0-9+/=]+)'
        pieces = {int(i): value for i, value in re.findall(prefix, output)}
        encoded = b''.join(pieces[i] for i in sorted(pieces))
        if len(encoded) != int(encoded_size):
            raise AssertionError('incomplete frame')
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) != int(size):
            raise AssertionError('frame length mismatch')
        result[(direction.decode(), int(seq))] = raw
    return result


def key(guest, code):
    for down in (True, False):
        guest.qmp('input-send-event', {'events': [{'type': 'key', 'data': {
            'down': down, 'key': {'type': 'qcode', 'data': code}}}]})
        pump(guest, .1)


def chord(guest, code):
    for down in (True,):
        guest.qmp('input-send-event', {'events': [{'type': 'key', 'data': {
            'down': down, 'key': {'type': 'qcode', 'data': 'ctrl'}}}]})
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
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('image', 'session', 'consumer', 'notes', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--case', required=True, choices=(
        'edit', 'no-edit', 'revoke', 'protect-document', 'protect-ancestor'))
    args = parser.parse_args()
    out = args.output.resolve()
    relative = out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    source = fixture()
    report = {'status': 'FAILED', 'case': args.case, 'events': [], 'checks': [],
              'inputs': {name: {'sha256': digest(getattr(args, name).read_bytes())}
                         for name in ('image', 'session', 'consumer', 'notes')},
              'synthetic_input_sha256': digest(source.encode()),
              'synthetic_input_utf16_units': len(source.encode('utf-16-le')) // 2}
    (out / 'synthetic-input.txt').write_text(source, encoding='utf-8')
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_ssg_live_') as temp:
            tmp = Path(temp)
            disk = tmp / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            for src, name in ((args.session, 'session'), (args.consumer, 'ssg-consumer'), (args.notes, 'notes')):
                transfer(disk, 'import', '/bin/' + name + '.elf', src)
            note = tmp / 'synthetic.txt'
            note.write_text(source, encoding='utf-8')
            transfer(disk, 'import', '/synthetic.txt', note)
            guest = Guest(args.image.resolve(), str(relative) + '/guest', work_disk=disk)
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            report['qemu_command_template'] = portable(guest.command, [
                ('XOS_IMAGE', args.image), ('XOS_QEMU', guest.command[0]),
                ('XOS_WORK_DISK', disk), ('XOS_QMP_SOCKET', guest.qmp_path)], strict=True)
            guest.expect(b'xos64> ', timeout=45)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=45)
            command(guest, 'demo quiet', b'demo tasks stopped')
            report['baseline_resources'] = resources(guest)
            command(guest, 'display-start', b'result=0')
            guest.expect(b'[display-service] ready')
            active = resources(guest)
            start = len(guest.output)
            mode = 'text-range-live' if args.case in ('edit', 'no-edit') else 'text-range-live-refusal'
            send_bytes(guest, f'exec-driver /bin/session.elf /synthetic.txt {mode} --text\r'.encode())
            guest.expect(b'QT_EDITOR_READY', start=start, timeout=120)
            guest.expect(b'SSG_TEST_OWNER_DOCUMENT', start=start, timeout=30)
            guest.expect(b'SSG_NOTES_EDIT_INJECTION_READY', start=start, timeout=120)
            report['events'].append('two_ranges_received_and_injection_ready')
            injection = {
                'edit': ('z', b'EDITOR_CHANGE'),
                'revoke': ('6', b'SSG_TEST_OWNER_REVOKED'),
                'protect-document': ('7', b'SSG_TEST_OWNER_DOCUMENT_PROTECTED'),
                'protect-ancestor': ('8', b'SSG_TEST_OWNER_ANCESTOR_PROTECTED'),
            }
            if args.case in injection:
                code, marker = injection[args.case]
                if args.case == 'edit':
                    key(guest, code)
                else:
                    chord(guest, code)
                guest.expect(marker, start=start, timeout=20)
                report['events'].append(('qmp_key_' if args.case == 'edit' else 'qmp_ctrl_') + code)
                report['events'].append(marker.decode())
            guest.expect(b'SSG_SESSION consumer_wait=0 outcome=1 code=0', start=start, timeout=180)
            output = bytes(guest.output)[start:]
            identities = re.search(rb'SSG_SESSION parent=(\d+) provider=(\d+) consumer=(\d+) instance=([0-9a-f]{32})', output)
            if not identities or len(set(identities.groups()[:3])) != 3:
                raise AssertionError('distinct process identities missing')
            report['processes'] = {'parent': int(identities[1]), 'provider': int(identities[2]),
                                   'consumer': int(identities[3]), 'instance': identities[4].decode()}
            parsed = frames(output)
            for (direction, seq), data in sorted(parsed.items()):
                (out / f'{seq:02d}-{direction.lower()}.bin').write_bytes(data)
            report['frame_count'] = len(parsed)
            report['owner_documents'] = [{'units': int(n), 'sha256': h.decode()} for n, h in
                re.findall(rb'SSG_TEST_OWNER_DOCUMENT units=(\d+) sha256=([0-9a-f]{64})', output)]
            report['transaction_markers'] = [line.decode() for line in output.splitlines()
                                             if line.startswith(b'SSG_TEXT_TRANSACTION ')]
            if args.case == 'edit':
                guest.expect(b'SSG_TEXT_TRANSACTION INVALID revision', start=start)
                guest.expect(b'SSG_TEXT_TRANSACTION DISCARDED', start=start)
                expected = 'z' + source
                if parsed.get(('TEXT', 0)) != expected.encode():
                    raise AssertionError('committed output differs from independent synthetic reference')
                guest.expect(b'SSG_TEST_OWNER_DOCUMENT units=', start=output.index(b'EDITOR_CHANGE') + start, timeout=20)
            elif args.case == 'no-edit':
                if b'RESET_REQUIRED' in output or b'INVALID revision' in output or parsed.get(('TEXT', 0)) != source.encode():
                    raise AssertionError('negative control unexpectedly reset or differed')
            else:
                status = b'DENIED' if args.case == 'revoke' else b'PROTECTED'
                if b'REFUSAL_CONFIRMED status=' + status not in output or ('TEXT', 0) in parsed:
                    raise AssertionError('restricted transaction was not rejected')
            key(guest, 'esc')
            if args.case == 'edit':
                guest.expect(b'EDITOR_UNSAVED_GUARD', start=start, timeout=30)
                guest.expect(b'EDITOR_POINT discard=', start=start, timeout=20)
                point = list(re.finditer(rb'EDITOR_POINT discard=(\d+),(\d+)', bytes(guest.output)[start:]))[-1]
                click(guest, *map(int, point.groups()))
            guest.expect(b'SSG_SESSION provider_wait=0 outcome=1 code=0', start=start, timeout=60)
            guest.expect_supervisor(start=start, timeout=60)
            report['resources_before'] = active
            report['resources_after'] = resources(guest)
            if report['resources_after'] != active:
                raise AssertionError('child or pipe resources did not return to baseline')
            report['checks'].extend(['distinct_processes', 'actual_pipe_frames', 'resource_baseline_restored'])
            report['status'] = 'GUEST_RUN_CAPTURED'
    except Exception as exc:
        report['error_type'] = type(exc).__name__
        report['error'] = str(exc)
        raise
    finally:
        if guest:
            (out / 'serial.log').write_bytes(bytes(guest.output))
            guest.close()
            report['qemu_exit_after_test_shutdown'] = guest.process.returncode
        (out / 'report.json').write_text(json.dumps(portable(report, [('XOS_TEST_OUT', out),
              ('XOS_IMAGE', args.image)], strict=True), indent=2) + '\n')
    print(report['status'], args.case, flush=True)


if __name__ == '__main__':
    main()
