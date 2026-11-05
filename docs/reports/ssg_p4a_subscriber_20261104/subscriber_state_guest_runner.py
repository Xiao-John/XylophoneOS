#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run directed Subscriber state-transition checks inside the XOS guest."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / 'tests'), str(root / 'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from ssg_public_paths import portable
from task_smoke import send_bytes
from work_disk import transfer


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('image', 'payload', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    relative = output.relative_to(root / 'build')
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'FAILED', 'inputs': {'image_sha256': sha(args.image),
               'payload_sha256': sha(args.payload)}, 'checks': []}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_p4a_state_') as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/state.elf', args.payload.resolve())
            guest = Guest(args.image.resolve(), str(relative / 'guest'), work_disk=disk,
                          iso=args.image.suffix.lower() == '.iso')
            report['qemu_version'] = subprocess.check_output(
                [guest.command[0], '--version'], text=True).splitlines()[0]
            report['qemu_sha256'] = sha(guest.command[0])
            report['qemu_command_template'] = portable(
                guest.command,
                [('XOS_IMAGE', args.image.resolve()), ('XOS_QEMU', guest.command[0]),
                 ('XOS_WORK_DISK', disk), ('XOS_QMP_SOCKET', guest.qmp_path)], strict=True)
            guest.expect(b'xos64> ', timeout=45)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=45)
            command(guest, 'demo quiet', b'demo tasks stopped')
            report['before'] = resources(guest)
            start = len(guest.output)
            send_bytes(guest, b'exec-driver /bin/state.elf\r')
            guest.expect(b'P4A_STATE_TEST_DONE', start=start, timeout=60)
            guest.expect_supervisor(start=start, timeout=30)
            report['after'] = resources(guest)
            output_bytes = bytes(guest.output)[start:]
            report['checks'] = [{'name': name.decode(), 'status': status.decode()}
                                for name, status in re.findall(rb'P4A_STATE_CHECK ([a-z_]+)=(PASS|FAIL)', output_bytes)]
            report['test_summary'] = next((line.decode() for line in output_bytes.splitlines()
                                           if line.startswith(b'P4A_STATE_TEST_DONE ')), '')
            report['resources_restored'] = report['before'] == report['after']
            if (not report['checks'] or any(item['status'] != 'PASS' for item in report['checks']) or
                not report['resources_restored'] or
                not re.search(rb'P4A_STATE_TEST_DONE checks=\d+ failures=0', output_bytes) or
                b'kind=exited code=0' not in output_bytes):
                raise AssertionError('state checks, process exit, or resources did not pass')
            report['status'] = 'PASSED_SCOPED'
    except Exception as error:
        report['error'] = repr(error)
    finally:
        if guest:
            (output / 'serial.log').write_bytes(guest.output)
            guest.close()
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], report.get('error', ''), flush=True)
    return 0 if report['status'] == 'PASSED_SCOPED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
