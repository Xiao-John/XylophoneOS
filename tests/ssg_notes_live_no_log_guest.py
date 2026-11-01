#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check that the ordinary live-range consumer does not log synthetic content."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from ssg_notes_live_edit_guest import fixture, key
from ssg_public_paths import portable
from task_smoke import send_bytes
from work_disk import transfer


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('image', 'session', 'consumer', 'notes', 'output'):
        p.add_argument('--' + n, type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    relative = out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    source = fixture().encode('utf-8')
    report = {'status': 'FAILED', 'synthetic_input_sha256': hashlib.sha256(source).hexdigest(),
              'inputs': {n: hashlib.sha256(getattr(a, n).read_bytes()).hexdigest()
                         for n in ('image', 'session', 'consumer', 'notes')}}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_ssg_no_log_') as tmp:
            tmp = Path(tmp)
            disk = tmp / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            for src, name in ((a.session, 'session'), (a.consumer, 'ssg-consumer'), (a.notes, 'notes')):
                transfer(disk, 'import', '/bin/' + name + '.elf', src)
            note = tmp / 'input.txt'
            note.write_bytes(source)
            transfer(disk, 'import', '/synthetic.txt', note)
            guest = Guest(a.image.resolve(), str(relative) + '/guest', work_disk=disk)
            report['qemu_command_template'] = portable(guest.command, [('XOS_QEMU', guest.command[0]),
                ('XOS_IMAGE', a.image), ('XOS_WORK_DISK', disk), ('XOS_QMP_SOCKET', guest.qmp_path)], strict=True)
            guest.expect(b'xos64> ', timeout=45)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=45)
            command(guest, 'demo quiet', b'demo tasks stopped')
            command(guest, 'display-start', b'result=0')
            guest.expect(b'[display-service] ready')
            before = resources(guest)
            start = len(guest.output)
            send_bytes(guest, b'exec-driver /bin/session.elf /synthetic.txt text-range-live --text\r')
            guest.expect(b'SSG_TEXT_TRANSACTION COMMITTED units=4114 revision=0', start=start, timeout=120)
            guest.expect(b'SSG_SESSION consumer_wait=0 outcome=1 code=0', start=start, timeout=60)
            key(guest, 'esc')
            guest.expect(b'SSG_SESSION provider_wait=0 outcome=1 code=0', start=start, timeout=60)
            guest.expect_supervisor(start=start, timeout=60)
            output = bytes(guest.output)[start:]
            if b'SSG_FRAME_' in output or b'A' * 200 in output or b'RESET_REQUIRED' in output:
                raise AssertionError('unexpected frame/content/reset in ordinary live mode')
            after = resources(guest)
            if before != after:
                raise AssertionError('resources did not return to baseline')
            report.update(status='PASSED', resources_before=before, resources_after=after,
                          checks=['no_frame_log', 'no_synthetic_document_text_in_log',
                                  'no_reset_without_edit', 'resource_baseline_restored'])
    finally:
        if guest:
            (out / 'serial.log').write_bytes(bytes(guest.output))
            guest.close()
            report['qemu_exit_after_test_shutdown'] = guest.process.returncode
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'])


if __name__ == '__main__':
    main()
