#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the bounded SceneStream regression in a real XOS guest."""
import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes
from work_disk import transfer

parser = argparse.ArgumentParser()
for name in ('image', 'payload', 'output'):
    parser.add_argument('--' + name, type=Path, required=True)
parser.add_argument('--expected-checks', type=int, default=12)
parser.add_argument('--dash', type=Path)
args = parser.parse_args()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
receipt = json.loads(args.payload.with_suffix('.receipt.json').read_text())
assert sha(args.payload) == receipt['elf_sha256']
for name, digest in receipt['inputs'].items():
    assert sha(Path(name)) == digest, name
report = {'status': 'FAILED', 'image_sha256': sha(args.image),
          'payload_sha256': sha(args.payload), 'checks': []}
guest = None
try:
    with tempfile.TemporaryDirectory(prefix='xos_ssg_diff_') as tmp:
        disk = Path(tmp) / 'work.img'
        create_fat32(disk, 512)
        transfer(disk, 'mkdir', '/bin')
        transfer(disk, 'import', '/bin/ssgdiff.elf', args.payload)
        if args.dash:
            transfer(disk, 'import', '/bin/dash', args.dash)
            script=Path(tmp)/'ssg-diff-dash.sh'
            script.write_text('/bin/ssgdiff.elf\necho SSG_DIFF_DASH_STATUS:$?\n')
            transfer(disk, 'import', '/ssg-diff-dash.sh', script)
            report['dash_sha256']=sha(args.dash)
        guest = Guest(args.image.resolve(), str(out.relative_to(ROOT / 'build')) + '/guest', work_disk=disk)
        report['qemu_command'] = guest.command
        guest.expect(b'xos64> ', timeout=45)
        send_bytes(guest, b'run\r')
        guest.expect_supervisor(trace=True, timeout=45)
        command(guest, 'demo quiet', b'demo tasks stopped', timeout=20)
        baseline = resources(guest)
        start = len(guest.output)
        send_bytes(guest, b'exec-file /bin/ssgdiff.elf\r')
        marker=guest.expect_any((b'SSG_DIFF_TEST_DONE failures=', b'kind=faulted', b'kind=killed'), start=start, timeout=90)
        if marker!=b'SSG_DIFF_TEST_DONE failures=':
            raise AssertionError('probe terminated before reporting its checks: '+marker.decode())
        guest.expect_supervisor(start=start, timeout=45)
        output = bytes(guest.output)[start:]
        report['checks'] = [{'name': n.decode(), 'status': s.decode()}
                            for n, s in re.findall(rb'SSG_DIFF_CHECK ([a-z_]+)=(PASS|FAIL)', output)]
        report['baseline_resources'] = baseline
        report['after_resources'] = resources(guest)
        report['status'] = 'PASSED' if (len(report['checks']) == args.expected_checks and
            all(item['status'] == 'PASS' for item in report['checks']) and
            report['baseline_resources'] == report['after_resources'] and
            b'kind=exited code=0' in output) else 'FAILED'
        if args.dash:
            start=len(guest.output);send_bytes(guest,b'exec-driver /bin/dash /ssg-diff-dash.sh\r')
            guest.expect(b'SSG_DIFF_TEST_DONE failures=0',start=start,timeout=90)
            guest.expect(b'SSG_DIFF_DASH_STATUS:0',start=start,timeout=30)
            guest.expect_supervisor(start=start,timeout=30)
            output=bytes(guest.output)[start:]
            dash_checks=re.findall(rb'SSG_DIFF_CHECK ([a-z_]+)=(PASS|FAIL)',output)
            report['dash_checks']=[{'name':n.decode(),'status':s.decode()} for n,s in dash_checks]
            report['dash_after_resources']=resources(guest)
            if (len(dash_checks)!=args.expected_checks or any(s!=b'PASS' for _,s in dash_checks)
                    or report['dash_after_resources']!=baseline):
                report['status']='FAILED'
except Exception as error:
    report['error'] = repr(error)
    raise
finally:
    if guest:
        guest.close()
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
print(report['status'], len(report['checks']), 'checks')
sys.exit(0 if report['status'] == 'PASSED' else 1)
