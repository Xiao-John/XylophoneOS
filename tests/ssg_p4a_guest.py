#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise P4A subscription cases with independent XOS/QEMU processes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / 'tests'), str(root / 'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from ssg_p3b_guest import fixture, key, chord, click
from ssg_public_paths import portable
from task_smoke import send_bytes
from work_disk import transfer

cases = ('first', 'notes-edit', 'browser-scroll', 'notes-revoke',
         'protect-document', 'protect-ancestor', 'browser-exit', 'notes-exit',
         'backpressure', 'corrupt-frame', 'stop', 'cancel-inflight', 'wrong-ack', 'duplicate-ack',
         'premature-eof')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('image', 'supervisor', 'browser', 'notes', 'subscriber', 'input', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--case', choices=cases, default='first')
    args = parser.parse_args()
    output = args.output.resolve()
    relative = output.relative_to(root / 'build')
    output.mkdir(parents=True, exist_ok=False)
    report = {
        'status': 'FAILED',
        'scenario': args.case,
        'inputs': {name: {'sha256': sha(getattr(args, name).resolve())}
                   for name in ('image', 'supervisor', 'browser', 'notes', 'subscriber', 'input')},
        'events': [],
    }
    started = time.monotonic()
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_p4a_') as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512)
            for directory in ('/bin', '/web'):
                transfer(disk, 'mkdir', directory)
            for source, destination in (
                (args.supervisor, '/bin/multi.elf'),
                (args.browser, '/bin/browser.elf'),
                (args.notes, '/bin/notes.elf'),
                (args.subscriber, '/bin/ssg_subscriber.elf'),
                (args.input, '/web/ssg.html'),
            ):
                transfer(disk, 'import', destination, source.resolve())
            notes = output / 'synthetic.txt'
            notes.write_text(fixture(), encoding='utf-8')
            transfer(disk, 'import', '/synthetic.txt', notes)

            image = args.image.resolve()
            image_is_iso = image.suffix.lower() == '.iso'
            report['image_format'] = 'iso' if image_is_iso else 'floppy'
            guest = Guest(image, str(relative / 'guest'), work_disk=disk, iso=image_is_iso)
            report['qemu_version'] = subprocess.check_output(
                [guest.command[0], '--version'], text=True).splitlines()[0]
            report['qemu_sha256'] = sha(Path(guest.command[0]))
            report['qemu_command_template'] = portable(
                guest.command,
                [('XOS_IMAGE', image), ('XOS_QEMU', guest.command[0]),
                 ('XOS_WORK_DISK', disk), ('XOS_QMP_SOCKET', guest.qmp_path)], strict=True)
            guest.expect(b'xos64> ', timeout=45)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=45)
            command(guest, 'demo quiet', b'demo tasks stopped')
            command(guest, 'display-start', b'result=0')
            guest.expect(b'[display-service] ready', timeout=30)
            report['before'] = resources(guest)

            cycles = 3 if args.case not in ('first', 'backpressure', 'corrupt-frame', 'wrong-ack', 'duplicate-ack', 'premature-eof') else 1
            if args.case == 'cancel-inflight':
                mode = '--test-watch-cancel'
            else:
                mode = '--test-watch-browser' if args.case in (
                    'first', 'browser-scroll', 'browser-exit', 'backpressure', 'corrupt-frame',
                    'wrong-ack', 'duplicate-ack', 'premature-eof') else '--test-watch-notes'
            duration = 120 if args.case == 'backpressure' else 240
            command_line = (
                'exec-driver /bin/multi.elf /web/ssg.html /synthetic.txt ' + mode +
                ' --browser-text --notes-text --watch --watch-cycles ' + str(cycles) +
                ' --watch-interval 1 --watch-duration ' + str(duration) +
                ' --watch-timeout 60 --watch-subscriber' +
                (' --watch-subscriber-pause' if args.case == 'backpressure' else '') +
                (' --watch-subscriber-corrupt-first' if args.case == 'corrupt-frame' else '') +
                (' --watch-subscriber-wrong-ack' if args.case == 'wrong-ack' else '') +
                (' --watch-subscriber-duplicate-ack' if args.case == 'duplicate-ack' else '') +
                (' --watch-subscriber-close-before-first-event' if args.case == 'premature-eof' else '') +
                (' --test-watch-stop-control' if args.case == 'stop' else '') + '\r'
            )
            start = len(guest.output)
            send_bytes(guest, command_line.encode())
            guest.expect(b'P4A_SUBSCRIBER_STARTED ', start=start, timeout=150)

            actions = {
                'notes-edit': [('z', False, b'EDITOR_CHANGE'), ('x', False, b'EDITOR_CHANGE')],
                'browser-scroll': [('pgdn', False, b'BROWSER_SCROLL value='),
                                   ('pgdn', False, b'BROWSER_SCROLL value=')],
                'notes-revoke': [('6', True, b'SSG_TEST_OWNER_REVOKED')],
                'protect-document': [('7', True, b'SSG_TEST_OWNER_DOCUMENT_PROTECTED')],
                'protect-ancestor': [('8', True, b'SSG_TEST_OWNER_ANCESTOR_PROTECTED')],
                'browser-exit': [('esc', False, None)],
                'notes-exit': [('esc', False, None)],
            }.get(args.case, [])
            for index, (value, control_key, marker) in enumerate(actions, 1):
                guest.expect(f'P4A_CYCLE_READY cycle={index}'.encode(), start=start, timeout=300)
                offset = len(guest.output)
                if control_key:
                    chord(guest, value)
                else:
                    key(guest, value)
                if marker:
                    guest.expect(marker, start=offset, timeout=30)
                report['events'].append({'cycle': index, 'key': value,
                                         'control': control_key, 'serial_offset': offset})

            if args.case == 'premature-eof':
                guest.expect(b'P4A_SUBSCRIBER_STOP reason=PREMATURE_EOF browser_events=0 notes_events=0 events=0 acks_sent=0', start=start, timeout=30)
                guest.expect(b'P4A_SUBSCRIBER_EXIT reaped=1 cancelled=0 outcome=1 code=5 clean=0', start=start, timeout=30)
                guest.expect(b'P4A_PREMATURE_EOF_TEST before_initial=1 events_attempted=0 acknowledgements=0 subscriber_clean=0', start=start, timeout=30)
                guest.expect(b'P3B_CAPTURE_COMPLETE', start=start, timeout=30)
                key(guest, 'esc')
            elif args.case == 'backpressure':
                guest.expect(b'P4A_BACKPRESSURE_PROBE result=WOULD_BLOCK frame_bytes=4096 atomic=1', start=start, timeout=20)
                guest.expect(b'P4A_RECEIVE stream=1 slot=browser ', start=start, timeout=30)
                guest.expect(b'P4A_SUBSCRIBER_ACK status=UNKNOWN stream=1', start=start, timeout=20)
                guest.expect(b'P4A_WATCH_STOP reason=OUTPUT_ERROR cycles=0 events=0 attempted=1 acks=0 delivery=UNKNOWN resync=RESET_REQUIRED', start=start, timeout=20)
                guest.expect(b'P3B_CAPTURE_COMPLETE', start=start, timeout=30)
                key(guest, 'esc')
            elif args.case == 'corrupt-frame':
                guest.expect(b'P4A_SUBSCRIBER_RESET_REQUIRED reason=CHECKSUM_INVALID stream=1', start=start, timeout=30)
                guest.expect(b'P4A_SUBSCRIBER_ACK status=REJECTED stream=1', start=start, timeout=20)
                guest.expect(b'P4A_ACK stream=1 status=REJECTED proof=NOT_COMMITTED', start=start, timeout=20)
                guest.expect(b'P4A_SUBSCRIBER_EXIT reaped=1 cancelled=0 outcome=1 code=3 clean=0', start=start, timeout=20)
                guest.expect(b'P4A_WATCH_STOP reason=OUTPUT_ERROR cycles=0 events=0 attempted=1 acks=0 delivery=REJECTED resync=RESET_REQUIRED', start=start, timeout=20)
                guest.expect(b'P3B_CAPTURE_COMPLETE', start=start, timeout=30)
                key(guest, 'esc')
            elif args.case == 'wrong-ack':
                guest.expect(b'P4A_SUBSCRIBER_ACK status=SENT stream=1 ack_sequence=2', start=start, timeout=30)
                guest.expect(b'P4A_ACK_HEADER stream=1', start=start, timeout=30)
                guest.expect(b'ack_stream=2', start=start, timeout=20)
                guest.expect(b'P4A_WATCH_STOP reason=OUTPUT_ERROR cycles=0 events=0 attempted=1 acks=0 delivery=UNKNOWN resync=RESET_REQUIRED', start=start, timeout=20)
                guest.expect(b'P4A_SUBSCRIBER_STOP reason=PREMATURE_EOF browser_events=1 notes_events=0 events=1 acks_sent=1', start=start, timeout=20)
                guest.expect(b'P4A_SUBSCRIBER_EXIT reaped=1 cancelled=0 outcome=1 code=5 clean=0', start=start, timeout=20)
                guest.expect(b'P3B_CAPTURE_COMPLETE', start=start, timeout=30)
                key(guest, 'esc')
            elif args.case == 'duplicate-ack':
                guest.expect(b'P4A_SUBSCRIBER_ACK status=SENT stream=1 ack_sequence=1 duplicate=1', start=start, timeout=30)
                guest.expect(b'P4A_SEND stream=2 slot=notes ', start=start, timeout=30)
                guest.expect(b'P4A_ACK_HEADER stream=2', start=start, timeout=30)
                guest.expect(b'ack_stream=1', start=start, timeout=20)
                guest.expect(b'P4A_WATCH_STOP reason=OUTPUT_ERROR cycles=0 events=1 attempted=2 acks=1 delivery=UNKNOWN resync=RESET_REQUIRED', start=start, timeout=20)
                guest.expect(b'P3B_CAPTURE_COMPLETE', start=start, timeout=30)
                child_outcome = guest.expect_any((
                    b'P4A_SUBSCRIBER_EXIT reaped=1 cancelled=0 outcome=1 code=0 clean=1',
                    b'P4A_SUBSCRIBER_EXIT reaped=1 cancelled=0 outcome=1 code=4 clean=0'),
                    start=start, timeout=30)
                report['duplicate_ack_subscriber_outcome'] = child_outcome.decode()
                key(guest, 'esc')
            elif args.case == 'stop':
                guest.expect(b'P4A_CYCLE_READY cycle=2', start=start, timeout=300)
                guest.expect(b'P4A_SUBSCRIBER_STOP reason=SUPERVISOR_CLOSED events=4 acks_sent=4', start=start, timeout=30)
                guest.expect(b'P4A_WATCH_STOP reason=EXPLICIT_STOP cycles=2 events=4 attempted=4 acks=4 delivery=ACKED', start=start, timeout=30)
                guest.expect(b'P3B_CAPTURE_COMPLETE', start=start, timeout=30)
                key(guest, 'esc')
            elif args.case == 'cancel-inflight':
                guest.expect(b'P4A_CYCLE_READY cycle=1', start=start, timeout=120)
                guest.expect(b'P4A_SUBSCRIBER_STOP reason=SUPERVISOR_CLOSED events=2 acks_sent=2', start=start, timeout=60)
                guest.expect(b'P4A_WATCH_STOP reason=EXPLICIT_STOP cycles=1 events=2 attempted=2 acks=2 delivery=ACKED', start=start, timeout=30)
                guest.expect(b'P3B_CAPTURE_COMPLETE', start=start, timeout=30)
                key(guest, 'esc')
            else:
                guest.expect(f'P4A_CYCLE_READY cycle={cycles}'.encode(), start=start, timeout=300)
                guest.expect(f'P4A_SUBSCRIBER_STOP reason=SUPERVISOR_CLOSED events={cycles * 2} acks_sent={cycles * 2}'.encode(), start=start, timeout=30)
                guest.expect(f'P4A_WATCH_STOP reason=CYCLE_LIMIT cycles={cycles} events={cycles * 2} attempted={cycles * 2} acks={cycles * 2} delivery=ACKED'.encode(), start=start, timeout=30)
                guest.expect(b'P3B_CAPTURE_COMPLETE', start=start, timeout=30)
                if args.case not in ('browser-exit', 'notes-exit'):
                    key(guest, 'esc')
                    if args.case == 'notes-edit':
                        guest.expect(b'EDITOR_UNSAVED_GUARD', start=start, timeout=20)
                        guest.expect(b'EDITOR_POINT discard=', start=start, timeout=20)
                        match = list(re.finditer(rb'EDITOR_POINT discard=(\d+),(\d+)', bytes(guest.output)[start:]))[-1]
                        click(guest, int(match[1]), int(match[2]))
            if args.case not in ('backpressure', 'corrupt-frame', 'wrong-ack', 'duplicate-ack', 'premature-eof'):
                guest.expect(b'P4A_SUBSCRIBER_EXIT reaped=1 cancelled=0 outcome=1 code=0 clean=1', start=start, timeout=20)
            guest.expect_supervisor(start=start, timeout=60)
            report['after'] = resources(guest)
            output_bytes = bytes(guest.output)[start:]
            pipe_reuse = re.search(rb'P4A_PIPE_REUSE before=(\d+) after=(\d+) sampled=1 balanced=1', output_bytes)
            if not pipe_reuse or pipe_reuse[1] != pipe_reuse[2]:
                raise AssertionError('P4A Pipe capacity did not recover to its before-session count')
            thread_stats = {}
            for phase in ('before', 'after'):
                match = re.search(
                    rb'P4A_THREAD_STATS phase=' + phase.encode() +
                    rb' status=OBSERVED processes=(\d+) threads=(\d+) waiting=(\d+) results=(\d+) free_pages=(\d+) process_user_pages=(\d+) process_kernel_stack_pages=(\d+)',
                    output_bytes)
                if not match:
                    raise AssertionError('thread/page resource statistics are unavailable')
                thread_stats[phase] = list(map(int, match.groups()))
            stable_fields = (0, 1, 2, 3, 6)
            if any(thread_stats['before'][index] != thread_stats['after'][index] for index in stable_fields):
                raise AssertionError('process, thread, wait, result, or kernel-stack counts changed before exit')
            stale_probe = re.search(rb'P3B_STALE_TOKEN_REFUSED checked=4 denied=4 reused=0', output_bytes)
            capacity_probe = re.search(rb'P3B_PIPE_REUSE acquired=4 requested=4', output_bytes)
            if not stale_probe or not capacity_probe:
                raise AssertionError('four-pipe reuse or stale-token denial probe failed')
            report['pipe_capacity_available'] = {'before': int(pipe_reuse[1]), 'after': int(pipe_reuse[2])}
            report['thread_stats'] = thread_stats
            report['thread_stats_page_delta'] = {
                'free_pages': thread_stats['after'][4] - thread_stats['before'][4],
                'process_user_pages': thread_stats['after'][5] - thread_stats['before'][5],
            }
            report['stale_token_probe'] = '4/4_DENIED'
            process_ids = re.search(
                rb'P3B_BOTH_STARTED supervisor=(\d+) browser=(\d+) notes=(\d+).*?'
                rb'P4A_SUBSCRIBER_STARTED supervisor=(\d+) subscriber=(\d+)',
                output_bytes, re.S)
            if not process_ids:
                raise AssertionError('missing four guest process roles')
            identities = list(map(int, process_ids.groups()))
            if identities[0] != identities[3] or len({identities[0], identities[1], identities[2], identities[4]}) != 4:
                raise AssertionError('process roles are not independent')
            report['processes'] = dict(zip(('supervisor', 'browser', 'notes', 'subscriber'),
                                           (identities[0], identities[1], identities[2], identities[4])))
            report['events'] += [line.decode() for line in output_bytes.splitlines()
                                 if line.startswith((b'P4A_SEND ', b'P4A_RECEIVE ', b'P4A_ACK '))]
            report['source_exits'] = [line.decode() for line in output_bytes.splitlines()
                                      if line.startswith(b'P3B_SOURCE_EXIT ')]
            report['supervisor_exit'] = re.search(
                rb'\[wait\] pid=' + str(report['processes']['supervisor']).encode() + rb' kind=(\w+) code=(-?\d+)',
                output_bytes)
            if report['supervisor_exit']:
                report['supervisor_exit'] = {'kind': report['supervisor_exit'][1].decode(),
                                             'code': int(report['supervisor_exit'][2])}
            expected_exit = {'kind': 'exited', 'code': 1} if args.case in ('backpressure', 'corrupt-frame', 'wrong-ack', 'duplicate-ack', 'premature-eof') else {'kind': 'exited', 'code': 0}
            if report['supervisor_exit'] != expected_exit:
                raise AssertionError('supervisor exit did not match the scenario')
            report['resources_restored'] = report['before'] == report['after']
            if not report['resources_restored']:
                raise AssertionError('resource counters did not return to baseline')
            if len(report['source_exits']) != 2 or any('cancelled=1' in line for line in report['source_exits']):
                raise AssertionError('a provider was cancelled during the scenario')
            report['status'] = 'PASSED_SCOPED'
    except Exception as error:
        report['error'] = repr(error)
    finally:
        if guest:
            (output / 'serial.log').write_bytes(guest.output)
            guest.close()
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], report.get('error', ''), flush=True)
    return 0 if report['status'] == 'PASSED_SCOPED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
