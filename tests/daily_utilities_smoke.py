# SPDX-License-Identifier: Apache-2.0
"""Run the DU1/DU2 candidate ELFs under dash on an isolated XOS disk."""
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
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--tools', type=Path, required=True)
    p.add_argument('--dash', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    build = json.loads((a.tools / 'manifest.json').read_text())
    report = {'status': 'failed', 'image_sha256': hashlib.sha256(a.image.read_bytes()).hexdigest(),
              'tools_manifest_sha256': hashlib.sha256((a.tools / 'manifest.json').read_bytes()).hexdigest(),
              'dash_sha256': hashlib.sha256(a.dash.read_bytes()).hexdigest(), 'checks': []}
    try:
        with tempfile.TemporaryDirectory(prefix='xos_du12_') as tmp:
            folder = Path(tmp); disk = folder / 'disk.img'; create_fat32(disk, 512)
            for d in ('/usr', '/usr/bin', '/tmp', '/tests'): transfer(disk, 'mkdir', d)
            transfer(disk, 'import', '/usr/bin/dash', a.dash)
            for entry in build['tools']:
                source = a.tools / entry['name']
                assert hashlib.sha256(source.read_bytes()).hexdigest() == entry['elf_sha256']
                transfer(disk, 'import', entry['guest_path'], source)
            transfer(disk, 'import', '/tests/du12.sh', ROOT / 'tests/fixtures/daily_utilities/du12.sh')
            guest = Guest(a.image, 'daily_utilities', work_disk=disk)
            try:
                guest.expect(b'xos64> ', timeout=30); start = len(guest.output); send_bytes(guest, b'run\r')
                guest.expect_supervisor(start=start, timeout=40); pump(guest, .4)
                send_bytes(guest, b'demo quiet\r'); pump(guest, .4)
                start = len(guest.output); send_bytes(guest, b'dash /tests/du12.sh\r')
                guest.expect_supervisor(start=start, timeout=180)
                output = bytes(guest.output[start:])
                if b'DU12_OK' not in output:
                    raise AssertionError('daily utility script failed: ' + output[-4000:].decode('utf-8', 'replace'))
                start = len(guest.output); send_bytes(guest, b'exec-file /usr/bin/ls /tmp/du\r')
                guest.expect_supervisor(start=start, timeout=30)
                output = bytes(guest.output[start:])
                if b'head.txt' not in output or b'moved' not in output:
                    raise AssertionError('xsh explicit ls failed: ' + output[-2000:].decode('utf-8', 'replace'))
                start = len(guest.output); send_bytes(guest, b'sync\r'); guest.expect_supervisor(start=start, timeout=30)
                report['checks'].append('dash_operations_pipe_and_rejected_unsafe_cases')
                report['checks'].append('xsh_exec_file_ls')
            finally:
                guest.close()
            expected = {'ls.txt':b'data\n','all.txt':b'.\n..\n.secret\ndata\n',
                        'almost.txt':b'.secret\ndata\n','dir.txt':b'/tmp/du/a\n',
                        'cat.txt':b'one\ntwo\nthree\n','head.txt':b'one\ntwo\n',
                        'tail.txt':b'two\nthree\n', 'tail_pipe.txt':b'b\nc', 'head_pipe.txt':b'a\nb\n',
                        'wc.txt':b'3 3 14 /tmp/du/moved\n',
                        'tee.txt':b'hello\nagain\n','tee_out.txt':b'hello\n', 'tee_append_out.txt':b'again\n',
                        'base.txt':b'moved\n','parent.txt':b'/tmp/du\n'}
            for name, contents in expected.items():
                result = folder / name; transfer(disk, 'export', '/tmp/du/' + name, result)
                assert result.read_bytes() == contents, (name, result.read_bytes(), contents)
            report['checks'].append('offline_exact_output_bytes')
        report['status'] = 'passed'
    finally:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
