# SPDX-License-Identifier: Apache-2.0
"""F1 real serial editor byte-preservation and rejection checks on a private disk."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from task_smoke import pump, send_bytes
from work_disk import transfer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    report = {'status': 'failed', 'build_id': manifest['build_id'],
              'image_sha256': hashlib.sha256(args.image.read_bytes()).hexdigest(), 'checks': []}
    with tempfile.TemporaryDirectory(prefix='xos_f1_editor_') as temp:
        temp = Path(temp)
        disk, fixture, exported = temp / 'disk.img', temp / 'input', temp / 'output'
        fixture.write_bytes(b'first  \r\n\xff\x1braw\nlast')
        create_fat32(disk, 2048)
        transfer(disk, 'import', '/note.txt', fixture)
        guest = Guest(args.image, 'editor_f1', work_disk=disk)
        report['command'] = guest.command
        try:
            guest.expect(b'xos64> ', timeout=30)
            start = len(guest.output)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(start=start, timeout=40)
            pump(guest, 0.4)
            start = len(guest.output)
            send_bytes(guest, b'demo quiet\r')
            guest.expect(b'demo tasks', start=start, timeout=20)
            guest.expect_supervisor(start=start, timeout=20)

            def send(data, expected=b'| '):
                start = len(guest.output)
                send_bytes(guest, data + b'\r')
                guest.expect(expected, start=start, timeout=30)
                return bytes(guest.output[start:])

            send(b'edit note.txt', b'| ')
            output = send(b':p 2')
            assert b'2: \\xFF\\x1Braw' in output, output
            report['checks'].append('safe_display_of_invalid_and_control_bytes')
            send(b':r 3', b'text| ')
            send('最后'.encode())
            send(b':i 2', b'text| ')
            send('中文'.encode())
            send(b'::literal')
            send(b':i 2', b'text| ')
            output = send(b'\xff')
            assert b'invalid input' in output, output
            send(b':d 2')
            output = send(b':d 99')
            assert b'invalid line number' in output, output
            output = send(b':q')
            assert b'unsaved changes' in output, output
            report['checks'].append('line_operations_utf8_reject_and_dirty_guard')
            send(b':wq', b'xsh> ')
            start = len(guest.output)
            send_bytes(guest, b'sync\r')
            guest.expect(b'xsh> ', start=start, timeout=30)
        finally:
            guest.close()
        transfer(disk, 'export', '/note.txt', exported)
        expected = b'first  \r\n\xff\x1braw\n' + '最后'.encode() + b'\n:literal\n'
        assert exported.read_bytes() == expected, (exported.read_bytes(), expected)
        report['checks'].append('offline_exact_bytes_after_sync')
    report['status'] = 'passed'
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
