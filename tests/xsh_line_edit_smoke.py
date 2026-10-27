# SPDX-License-Identifier: Apache-2.0
"""Guest checks for Xshell line editing against an isolated FAT work disk."""
import argparse
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from task_smoke import pump, send_bytes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = {'status': 'failed', 'image_sha256': hashlib.sha256(args.image.read_bytes()).hexdigest(), 'checks': []}
    with tempfile.TemporaryDirectory(prefix='xos_line_edit_') as folder:
        disk = Path(folder) / 'work.img'
        create_fat32(disk, 512)
        guest = Guest(args.image, 'xsh_line_edit', work_disk=disk)
        try:
            guest.expect(b'xos64> ', timeout=40)
            send_bytes(guest, b'run\r')
            guest.expect(b'xsh> ', timeout=40)
            pump(guest, 1.5)

            def command(name, data, expected, timeout=20):
                start = len(guest.output)
                send_bytes(guest, data)
                guest.expect(expected, start=start, timeout=timeout)
                marker = guest.output.find(expected, start)
                guest.expect(b'xsh> ', start=marker + len(expected), timeout=timeout)
                report['checks'].append(name)

            command('insert_left', b'ac\x1b[Db\r', b'xsh: abc: not found')
            command('delete', b'abxc\x1b[D\x1b[D\x1b[3~\r', b'xsh: abc: not found')
            command('home_end', b'bc\x1b[Ha\x1b[Fz\r', b'xsh: abcz: not found')
            command('unicode_cursor', 'ab你c'.encode() + b'\x1b[D\x1b[D\x7fX\r', b'aX\xe4\xbd\xa0c: cannot read program')
            command('history', b'\x1b[A\r', b'aX\xe4\xbd\xa0c: cannot read program')
            command('history_draft', b'xy\x1b[A\x1b[Bz\r', b'xsh: xyz: not found')
            command('invalid_utf8', b'abc\xff\r', b'xsh: invalid UTF-8 input')
            command('incomplete_utf8', b'abc\xe4\xbd\r', b'xsh: invalid UTF-8 input')
            command('unknown_sequence', b'abc\x1b[999~\r', b'xsh: invalid UTF-8 input')
            command('crlf', b'abc\r\n', b'xsh: abc: not found')
            start = len(guest.output)
            send_bytes(guest, b'abc\x1b[')
            time.sleep(0.4)
            send_bytes(guest, b'D\r')
            guest.expect(b'xsh: invalid UTF-8 input', start=start)
            report['checks'].append('timed_out_sequence_rejected')
            report['status'] = 'passed'
        finally:
            guest.close()
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
