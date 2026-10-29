#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise xos-diag through dash and verify its exported fault report."""
import argparse, hashlib, json, re, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'scripts')]
from boot_smoke import Guest
from task_smoke import send_bytes, pump
from process_smoke import command
from make_work_disk import create_fat32
from work_disk import transfer
from fb2_symbolize import validate

p = argparse.ArgumentParser()
p.add_argument('--system', type=Path, required=True)
p.add_argument('--dash-manifest', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
manifest = json.loads((a.system / 'manifest.json').read_text())
for name, digest in manifest['sources'].items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
for name, item in manifest['artifacts'].items():
    assert hashlib.sha256((a.system / name).read_bytes()).hexdigest() == item['sha256'], name
dash = json.loads(a.dash_manifest.read_text())
dash_elf = ROOT / dash['elf']
assert hashlib.sha256(dash_elf.read_bytes()).hexdigest() == dash['sha256']
guest = None
report = {'status': 'failed', 'build_id': manifest['build_id'], 'dash_sha256': dash['sha256'], 'checks': []}
try:
    with tempfile.TemporaryDirectory(prefix='xos_fb12_dash_') as temp:
        tmp = Path(temp); disk = tmp / 'work.img'; create_fat32(disk, 512)
        for d in ('/usr', '/usr/bin', '/bin'): transfer(disk, 'mkdir', d)
        for dest, source in (('/usr/bin/dash', dash_elf), ('/usr/bin/xos-diag', a.system/'user_xos_diag.image.elf'), ('/bin/fault.elf', a.system/'user_fault.image.elf'), ('/bin/hello.elf', a.system/'user_hello.image.elf')):
            transfer(disk, 'import', dest, source)
        for name, line in (('normal', '(exec /usr/bin/xos-diag /bin/hello.elf); echo NORMAL:$?'), ('fault', '(exec /usr/bin/xos-diag /bin/fault.elf); echo FAULT:$?'), ('missing', '(exec /usr/bin/xos-diag /bin/missing); echo MISSING:$?')):
            script = tmp / (name + '.sh'); script.write_text(line + '\n')
            transfer(disk, 'import', '/bin/' + name + '.sh', script)
        guest = Guest(a.system/'xos.img', str(a.output.relative_to(ROOT/'build')) + '/dash', work_disk=disk, cpu='qemu64,+rdrand')
        guest.expect(b'xos64> ', timeout=45); send_bytes(guest, b'run\r'); guest.expect_supervisor(trace=True, timeout=45)
        command(guest, 'demo keep', b'demo: keep')
        for pid in (1, 3, 4): command(guest, f'kill {pid}', b'kill: accepted')
        pump(guest, .3)
        normal = command(guest, 'exec-driver /usr/bin/dash /bin/normal.sh', b'NORMAL:0', timeout=90)
        assert b'[fault-bundle] saved' not in normal
        report['checks'].append('dash_normal_exit_no_bundle')
        fault = command(guest, 'exec-driver /usr/bin/dash /bin/fault.sh', b'FAULT:128', timeout=90)
        assert b'[xos-diag] kind=faulted vector=14' in fault
        match = re.search(rb'\[fault-bundle\] saved (/FAULTS/[0-9a-f]{32})', fault); assert match, fault[-3000:]
        missing = command(guest, 'exec-driver /usr/bin/dash /bin/missing.sh', b'MISSING:127', timeout=90)
        assert b'[fault-bundle] saved' not in missing
        report['checks'].append('dash_missing_command_exit_127')
        direct = command(guest, 'exec-driver /usr/bin/xos-diag /bin/fault.elf', b'kind=exited code=128', timeout=90)
        assert b'[xos-diag] kind=faulted vector=14' in direct and b'[fault-bundle] saved /FAULTS/' in direct
        report['checks'].append('xsh_external_diagnostic_fault')
        command(guest, 'sync', b'sync=ok'); (a.output/'dash.serial.log').write_bytes(guest.output); guest.close(); guest = None
        bundle = a.output/'bundle'; bundle.mkdir(exist_ok=True)
        for name in ('report.json', 'image.json', 'context.json', 'manifest.json'):
            transfer(disk, 'export', match.group(1).decode()+'/'+name, bundle/name)
        result, image = validate(bundle)
        assert result['vector'] == 14 and image['sha256'] == hashlib.sha256((a.system/'user_fault.image.elf').read_bytes()).hexdigest()
        report['checks'].append('dash_fault_report_valid_and_bound_to_target')
        report['status'] = 'passed'
finally:
    if guest:
        (a.output/'failed.serial.log').write_bytes(guest.output); guest.close()
    (a.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
print('PASS dash FB1', len(report['checks']))
