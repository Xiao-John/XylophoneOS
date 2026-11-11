#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run current QtGui or Widgets through Interactium on a VM3 image."""
import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import pump, send_bytes
from work_disk import transfer


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'payload', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--kind', choices=('gui', 'widgets'), required=True)
    args = parser.parse_args()
    system, payload, out = (p.resolve() for p in (args.system, args.payload, args.output))
    out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((system / 'manifest.json').read_text())
    for path, digest in manifest['sources'].items():
        assert sha(ROOT / path) == digest, path
    for path, item in manifest['artifacts'].items():
        assert sha(system / path) == item['sha256'], path
    receipt = json.loads(payload.with_suffix('.receipt.json').read_text())
    assert sha(payload) == receipt['elf_sha256']
    for path, digest in receipt['inputs'].items():
        assert sha(Path(path)) == digest, path
    report = {'status': 'failed', 'kind': args.kind, 'build_id': manifest['build_id'],
              'image_sha256': sha(system / 'xos-install.iso'), 'elf_sha256': sha(payload),
              'receipt_sha256': sha(payload.with_suffix('.receipt.json')), 'checks': []}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_vm3_qt_') as tmp:
            disk = Path(tmp) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/qt.elf', payload)
            note = Path(tmp) / 'note.txt'
            note.write_bytes(b'VM3 Qt Widgets acceptance\n')
            transfer(disk, 'import', '/note.txt', note)
            guest = Guest(system / 'xos-install.iso', str(out.relative_to(ROOT / 'build')) + '/guest',
                          work_disk=disk, iso=True)
            report['qemu_command'] = guest.command
            guest.expect(b'xos64> ', timeout=60)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, 'demo quiet', b'demo tasks')
            baseline = resources(guest)
            report['baseline'] = baseline
            start = len(guest.output)
            launched = command(guest, 'interactium-start', b'[interactium-start] pid=', timeout=120)
            guest.expect(b'[interactium-service] ready', start=start, timeout=120)
            display = int(re.search(rb'\[display-start\] pid=(\d+)', launched)[1])
            compositor = int(re.search(rb'\[interactium-start\] pid=(\d+)', launched)[1])
            with_service = resources(guest)
            report['with_service'] = with_service
            start = len(guest.output)
            send_bytes(guest, b'exec-file /bin/qt.elf ' + (b'interactive' if args.kind == 'gui' else b'/note.txt') + b'\r')
            ready = b'QT_GUI_READY' if args.kind == 'gui' else b'QT_EDITOR_READY'
            event = guest.expect_any((ready, b'kind=exited code=', b'kind=faulted', b'kind=killed'),
                                     start=start, timeout=900)
            assert event == ready, bytes(guest.output)[start:][-3000:]
            guest.expect(b'[qpa-frame]', start=start, timeout=120)
            def key(code, down):
                guest.qmp('input-send-event', {'events': [{'type': 'key', 'data': {
                    'down': down, 'key': {'type': 'qcode', 'data': code}}}]})
            key('a', True); key('a', False)
            guest.expect(b'text=a' if args.kind == 'gui' else b'EDITOR_CHANGE', start=start, timeout=120)
            mouse_start = len(guest.output)
            guest.qmp('input-send-event', {'events': [
                {'type': 'rel', 'data': {'axis': 'x', 'value': 31}},
                {'type': 'rel', 'data': {'axis': 'y', 'value': 17}},
                {'type': 'btn', 'data': {'button': 'left', 'down': True}}]})
            guest.qmp('input-send-event', {'events': [{'type': 'btn', 'data': {'button': 'left', 'down': False}}]})
            guest.expect(b'kind=3', start=mouse_start, timeout=120)
            pump(guest, 1)
            guest.qmp('screendump', {'filename': str(out / 'screen.ppm')})
            from PIL import Image
            picture = Image.open(out / 'screen.ppm')
            assert picture.size == (800, 600)
            picture.save(out / 'screen.png')
            report['screenshot_sha256'] = sha(out / 'screen.png')
            report['checks'].append('qt_interactium_keyboard_mouse_and_screenshot')
            if args.kind == 'widgets':
                key('ctrl', True); key('s', True); key('s', False); key('ctrl', False)
                guest.expect(b'EDITOR_SAVE_OK', start=start, timeout=120)
            key('esc', True); key('esc', False)
            guest.expect(b'kind=exited code=0', start=start, timeout=120)
            guest.expect_supervisor(start=start, timeout=90)
            assert resources(guest) == with_service
            report['checks'].append('client_exit_reclaims_resources')
            command(guest, f'kill {compositor}', b'kill: accepted')
            command(guest, f'wait {compositor}', b'kind=killed', timeout=120)
            command(guest, 'exec gfxdemo stop', b'kind=exited code=0', timeout=120)
            command(guest, f'wait {display}', b'kind=exited code=0', timeout=120)
            assert resources(guest) == baseline
            report['checks'].append('services_reclaim_resources')
            report['status'] = 'passed'
    finally:
        if guest:
            (out / 'guest.serial.log').write_bytes(guest.output)
            guest.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS VM3 Qt', args.kind)


if __name__ == '__main__':
    main()
