#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Repeat the real denied Browser request and require both processes to exit."""
import argparse
import base64
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
from task_smoke import pump, send_bytes
from work_disk import transfer


def response(data):
    match = re.search(rb'SSG_FRAME_BEGIN RESP 1 (\d+) (\d+)', data)
    if not match or b'SSG_FRAME_END RESP 1' not in data:
        raise AssertionError('missing response frame')
    chunks = {int(offset): chunk for offset, chunk in
              re.findall(rb'SSG_FRAME_PART RESP 1 (\d+) ([A-Za-z0-9+/=]+)', data)}
    encoded = b''.join(chunks[offset] for offset in sorted(chunks))
    if len(encoded) != int(match[2]):
        raise AssertionError('incomplete response frame')
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) != int(match[1]):
        raise AssertionError('response length mismatch')
    return json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('image', 'session', 'browser', 'consumer', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.rounds <= 100:
        parser.error('rounds must be between 1 and 100')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'FAILED', 'requested_rounds': args.rounds, 'completed_rounds': 0}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_ssg_exit_') as temporary:
            temporary = Path(temporary)
            disk = temporary / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            for source, name in ((args.session, 'session'), (args.browser, 'browser'),
                                 (args.consumer, 'ssg-consumer')):
                transfer(disk, 'import', '/bin/' + name + '.elf', source)
            transfer(disk, 'mkdir', '/web')
            page = temporary / 'ssg.html'
            page.write_text('<html><body><h1>Visible Alpha</h1><p>Protected text</p></body></html>')
            transfer(disk, 'import', '/web/ssg.html', page)
            guest = Guest(args.image.resolve(), str(out.relative_to(ROOT / 'build')) + '/guest', work_disk=disk)
            guest.expect(b'xos64> ', timeout=45)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=45)
            command(guest, 'demo quiet', b'demo tasks stopped')
            baseline = resources(guest)
            started = command(guest, 'display-start', b'result=0')
            service = int(re.search(rb'\[display-start\] pid=(\d+)', started)[1])
            guest.expect(b'[display-service] ready')
            active = resources(guest)
            for index in range(args.rounds):
                begin = len(guest.output)
                send_bytes(guest, b'exec-driver /bin/session.elf /web/ssg.html snapshot --browser content\r')
                guest.expect(b'SSG_SESSION consumer_wait=0 outcome=1 code=1', start=begin, timeout=100)
                guest.expect(b'BROWSER_READY', start=begin, timeout=60)
                result = response(bytes(guest.output)[begin:])
                if result.get('status') != 'DENIED' or 'nodes' in result:
                    raise AssertionError('protected Browser content was not denied')
                for down in (True, False):
                    guest.qmp('input-send-event', {'events': [{'type': 'key', 'data':
                        {'down': down, 'key': {'type': 'qcode', 'data': 'esc'}}}]})
                pump(guest, .1)
                guest.expect(b'SSG_SESSION provider_wait=0 outcome=1 code=0', start=begin, timeout=60)
                guest.expect_supervisor(start=begin, timeout=60)
                if resources(guest) != active:
                    raise AssertionError('resources did not return to active baseline')
                report['completed_rounds'] = index + 1
                print('PASS denied-consumer exit', index + 1, flush=True)
            command(guest, 'exec gfxdemo stop', b'kind=exited code=0')
            command(guest, f'wait {service}', b'kind=exited code=0')
            if resources(guest) != baseline:
                raise AssertionError('display resources did not return to baseline')
            report['status'] = 'PASSED_SCOPED'
    except Exception as error:
        report['error'] = repr(error)
    finally:
        if guest is not None:
            (out / 'serial.log').write_bytes(guest.output)
            guest.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], flush=True)
    return 0 if report['status'] == 'PASSED_SCOPED' else 1


if __name__ == '__main__':
    sys.exit(main())
