#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Restart both providers in one XOS boot and submit the old Browser instance."""
import argparse
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
from ssg_p3b_guest import fixture, key
from ssg_p3b_verify import frames
from task_smoke import send_bytes
from work_disk import transfer


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('image', 'supervisor', 'browser', 'notes', 'input', 'browser-receipt', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    relative = out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'FAILED', 'scope': 'two sequential sessions within one XOS boot', 'sessions': []}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_p3b_restart_') as temp:
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
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            report['qemu_sha256'] = sha(Path(guest.command[0]))
            report['qemu_command_template'] = portable(guest.command, [
                ('XOS_IMAGE', a.image), ('XOS_QEMU', guest.command[0]), ('XOS_WORK_DISK', disk),
                ('XOS_QMP_SOCKET', guest.qmp_path)], strict=True)
            guest.expect(b'xos64> ', timeout=45)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=45)
            command(guest, 'demo quiet', b'demo tasks stopped')
            command(guest, 'display-start', b'result=0')
            guest.expect(b'[display-service] ready')
            active = resources(guest)
            old_instance = None
            for i in (1, 2):
                case_dir = out / f'session-{i}'
                case_dir.mkdir()
                (case_dir / 'browser.receipt.json').write_bytes(a.browser_receipt.read_bytes())
                (case_dir / 'synthetic-input.txt').write_text(fixture(), encoding='utf-8')
                start = len(guest.output)
                mode = '' if i == 1 else ' --old-instance ' + old_instance
                mode += ' --browser-text --notes-text'
                send_bytes(guest, ('exec-driver /bin/multi.elf /web/ssg.html /synthetic.txt' + mode + '\r').encode())
                guest.expect(b'P3B_BOTH_STARTED', start=start, timeout=150)
                guest.expect(b'P3B_CAPTURE_COMPLETE', start=start, timeout=360)
                key(guest, 'esc')
                guest.expect(b'P3B_SOURCE_EXIT slot=notes', start=start, timeout=60)
                guest.expect_supervisor(start=start, timeout=60)
                output = bytes(guest.output)[start:]
                after = resources(guest)
                identity = re.search(rb'P3B_BOTH_STARTED supervisor=(\d+) browser=(\d+) notes=(\d+)', output)
                if not identity:
                    raise AssertionError('missing process identities')
                pids = dict(zip(('supervisor', 'browser', 'notes'), map(int, identity.groups())))
                wait = re.search(rb'\[wait\] pid=' + str(pids['supervisor']).encode() + rb' kind=(\w+) code=(-?\d+)', output)
                supervisor_exit = {'kind': wait[1].decode(), 'code': int(wait[2])} if wait else None
                case = {'status': 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION', 'case': 'baseline' if i == 1 else 'old-instance', 'processes': pids,
                        'supervisor_exit': supervisor_exit,
                        'inputs': {name: {'sha256': sha(getattr(a, name))} for name in ('image', 'supervisor', 'browser', 'notes', 'input')},
                        'resources_restored': active == after,
                        'source_exits': [line.decode() for line in output.splitlines() if line.startswith(b'P3B_SOURCE_EXIT ')]}
                if i == 2:
                    case['old_instance'] = old_instance
                (case_dir / 'serial.log').write_bytes(output)
                (case_dir / 'report.json').write_text(json.dumps(case, indent=2) + '\n')
                aggregate = frames(output)[('aggregate', 'BASELINE', 0)]
                current = next(v['instance'] for v in aggregate['sources'] if v['slot'] == 'browser')
                report['sessions'].append({'processes': pids, 'browser_instance': current,
                                           'resources_restored': active == after, 'source_exits': case['source_exits']})
                if i == 1:
                    old_instance = current
                elif current == old_instance or pids['browser'] == report['sessions'][0]['processes']['browser']:
                    raise AssertionError('Browser process/instance was reused')
            subprocess.run([sys.executable, str(ROOT / 'tests/ssg_p3b_verify.py'), str(out / 'session-1'),
                            '--browser-receipt', str(a.browser_receipt)], cwd=ROOT, check=True)
            subprocess.run([sys.executable, str(ROOT / 'tests/ssg_p3b_old_instance_verify.py'), str(out / 'session-2'),
                            '--previous', str(out / 'session-1')], cwd=ROOT, check=True)
            if not all(v['resources_restored'] and all('reaped=1 cancelled=0 outcome=1 code=0' in line for line in v['source_exits']) for v in report['sessions']):
                raise AssertionError('session resources or exit outcome')
            report['status'] = 'PASSED_SCOPED'
    except Exception as error:
        report['error_type'] = type(error).__name__
        report['error'] = str(error)
    finally:
        if guest:
            (out / 'serial.log').write_bytes(guest.output)
            guest.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], report.get('error', ''))
    return 0 if report['status'] == 'PASSED_SCOPED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
