#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the engine-neutral substitution and invalidation contract in the real XOS guest."""
import argparse
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes
from work_disk import transfer

p = argparse.ArgumentParser(description=__doc__)
for name in ('image', 'payload', 'output'):
    p.add_argument('--' + name, type=Path, required=True)
a = p.parse_args()
out = a.output.resolve()
relative = out.relative_to(ROOT / 'build')
out.mkdir(parents=True, exist_ok=False)
report = {'status': 'FAILED', 'checks': []}
guest = None
try:
    with tempfile.TemporaryDirectory(prefix='xos_p3c_contract_') as temp:
        disk = Path(temp) / 'work.img'
        create_fat32(disk, 512)
        transfer(disk, 'mkdir', '/bin')
        transfer(disk, 'import', '/bin/probe.elf', a.payload)
        guest = Guest(a.image.resolve(), str(relative) + '/guest', work_disk=disk)
        guest.expect(b'xos64> ', timeout=45)
        send_bytes(guest, b'run\r')
        guest.expect_supervisor(trace=True, timeout=45)
        command(guest, 'demo quiet', b'demo tasks stopped')
        report['before'] = resources(guest)
        start = len(guest.output)
        send_bytes(guest, b'exec-driver /bin/probe.elf\r')
        guest.expect(b'P3C_CONTRACT_DONE', start=start, timeout=60)
        guest.expect_supervisor(start=start, timeout=60)
        report['after'] = resources(guest)
        output = bytes(guest.output)[start:]
        report['checks'] = [{'name': n.decode(), 'status': s.decode()} for n, s in re.findall(rb'P3C_CONTRACT_CHECK ([a-z_]+)=(PASS|FAIL)', output)]
        if len(report['checks']) == 32 and all(v['status'] == 'PASS' for v in report['checks']) and report['before'] == report['after'] and b'P3C_CONTRACT_DONE checks=32 failures=0' in output and b'kind=exited code=0' in output:
            report['status'] = 'PASSED_SCOPED'
finally:
    if guest:
        (out / 'serial.log').write_bytes(guest.output)
        guest.close()
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
print(report['status'])
raise SystemExit(0 if report['status'] == 'PASSED_SCOPED' else 1)
