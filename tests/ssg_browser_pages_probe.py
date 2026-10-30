#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Record a Browser paging observation using explicitly supplied artifacts.

This probe does not establish completeness: the frames require an independent
model oracle and rendering/interaction qualification before they are a baseline.
"""
import argparse, base64, hashlib, json, os, re, sys, tempfile, traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from process_smoke import command, resources
from task_smoke import send_bytes

p = argparse.ArgumentParser(description=__doc__)
for name in ('image', 'session', 'browser', 'consumer', 'output', 'input'):
    p.add_argument('--' + name, type=Path, required=True)
a = p.parse_args()
inputs = {name: getattr(a, name).resolve(strict=True) for name in ('image', 'session', 'browser', 'consumer', 'input')}
out = a.output.resolve()
out.mkdir(parents=True, exist_ok=False)
def sha(data): return hashlib.sha256(data).hexdigest()
report = {'status': 'FAILED', 'qualification': 'NOT_RUN', 'inputs': {
    name: {'path': str(path), 'sha256': sha(path.read_bytes())} for name, path in inputs.items()}}
# Preserve the exact fixture that is actually imported, even if the original changes.
fixture = out / 'input.html'
fixture.write_bytes(inputs['input'].read_bytes())
report['inputs']['input']['sha256'] = sha(fixture.read_bytes())
report['inputs']['probe'] = {'path': str(Path(__file__).resolve()), 'sha256': sha(Path(__file__).read_bytes())}
g = None
try:
    with tempfile.TemporaryDirectory(prefix='xos_p2e_') as tmp:
        disk = Path(tmp) / 'work.img'
        create_fat32(disk, 512)
        transfer(disk, 'mkdir', '/bin'); transfer(disk, 'mkdir', '/web')
        for name, dest in (('session', 'session'), ('consumer', 'ssg-consumer'), ('browser', 'browser')):
            transfer(disk, 'import', '/bin/' + dest + '.elf', inputs[name])
        transfer(disk, 'import', '/web/ssg.html', fixture)
        # Guest writes its own logs relative to build; .. permits arbitrary output directories.
        guest_name = os.path.relpath(out / 'qemu', ROOT / 'build')
        g = Guest(inputs['image'], guest_name, work_disk=disk)
        report['qemu_command'] = g.command
        qemu = Path(g.command[0]).resolve(strict=True)
        report['inputs']['qemu'] = {'path': str(qemu), 'sha256': sha(qemu.read_bytes())}
        g.expect(b'xos64> ', timeout=45); send_bytes(g, b'run\r')
        g.expect_supervisor(trace=True, timeout=45)
        command(g, 'demo quiet', b'demo tasks stopped'); report['baseline'] = resources(g)
        command(g, 'display-start', b'result=0'); g.expect(b'[display-service] ready')
        report['display'] = resources(g)
        start = len(g.output)
        send_bytes(g, b'exec-driver /bin/session.elf /web/ssg.html browser-pages --browser --text\r')
        g.expect(b'SSG_PAGED_CONSUMER_DONE', start=start, timeout=150)
        g.qmp('input-send-event', {'events': [
            {'type':'key','data':{'down':down,'key':{'type':'qcode','data':'esc'}}} for down in (True, False)]})
        g.expect(b'SSG_SESSION consumer_wait=', start=start, timeout=60)
        g.expect(b'SSG_SESSION provider_wait=', start=start, timeout=60)
        g.expect_supervisor(start=start, timeout=60); report['after'] = resources(g)
        report['consumer_done'] = [line.decode() for line in bytes(g.output)[start:].splitlines() if b'SSG_PAGED_CONSUMER_DONE' in line]
        report['status'] = 'OBSERVED'
except Exception as error:
    report['error'] = repr(error)
    traceback.print_exc()
finally:
    if g:
        data = bytes(g.output)
        (out / 'serial.log').write_bytes(data)
        frames = []
        seen = set()
        try:
            for direction, seq, size, encoded_size in re.findall(rb'SSG_FRAME_BEGIN (REQ|RESP) (\d+) (\d+) (\d+)', data):
                parts = re.findall(rb'SSG_FRAME_PART ' + direction + rb' ' + seq + rb' (\d+) ([A-Za-z0-9+/=]+)', data)
                identity = (direction, seq)
                if identity in seen: raise ValueError('duplicate frame header')
                seen.add(identity)
                offsets = [int(offset) for offset, _ in parts]
                if len(offsets) != len(set(offsets)):
                    raise ValueError('duplicate frame part')
                encoded = b''
                for offset, chunk in sorted((int(offset), chunk) for offset, chunk in parts):
                    if offset != len(encoded): raise ValueError('non-contiguous frame parts')
                    encoded += chunk
                if len(encoded) != int(encoded_size) or not re.search(rb'SSG_FRAME_END ' + direction + b' ' + seq + rb'\b', data):
                    raise ValueError('incomplete frame')
                payload = base64.b64decode(encoded, validate=True)
                if len(payload) != int(size): raise ValueError('frame length mismatch')
                json.loads(payload)
                name = f'{int(seq):02d}-{direction.decode().lower()}.json'
                (out / name).write_bytes(payload)
                frames.append({'file': name, 'sha256': sha(payload), 'bytes': len(payload)})
            report['frames'] = frames
            if report['status'] == 'OBSERVED' and not frames:
                raise ValueError('no recorded frames')
            if report['status'] == 'OBSERVED':
                responses = [json.loads((out / f['file']).read_bytes()) for f in frames if f['file'].endswith('-resp.json')]
                if not responses or any(r.get('status') != 'OK' for r in responses):
                    raise ValueError('page response failed')
                for i, r in enumerate(responses):
                    if (r.get('pageSequence') != str(i + 1) or r.get('hasData') != bool(r.get('nodes')) or
                        r.get('hasNext') == r.get('complete') or r.get('traversalComplete') != r.get('complete') or
                        r.get('stopReason') != ('EXHAUSTED' if r.get('complete') else 'PAGE_BUDGET')):
                        raise ValueError('inconsistent completion fields')
                if any(r.get('complete') for r in responses[:-1]) or not responses[-1].get('complete'):
                    raise ValueError('missing or premature end')
                report['page_node_counts'] = [len(r['nodes']) for r in responses]
        except Exception as error:
            report['status'] = 'FAILED'; report['frame_error'] = repr(error)
        g.close()
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
if report['status'] != 'OBSERVED': sys.exit(1)
