"""Exercise the deployed Aurora desktop through real QEMU PS/2 input and QMP.

Works on Windows as well as POSIX: serial output uses a reader thread, not
selectors on Windows anonymous pipes. Never imports into or edits a live disk.
"""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from run_qemu import qemu_command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disk', type=Path, required=True)
    parser.add_argument('--iso', type=Path, default=ROOT / 'build/xos-install.iso')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/aurora_desktop_rewrite/guest')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    command = qemu_command(args.iso.resolve(), iso=True,
                           display='none', work_disk=args.disk.resolve())
    command += ['-qmp', f'tcp:127.0.0.1:{port},server=on,wait=off']
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, bufsize=0)
    output = bytearray()
    def read():
        with (out / 'serial.log').open('wb') as log:
            while True:
                data = process.stdout.read(4096)
                if not data:
                    break
                output.extend(data)
                log.write(data)
                log.flush()
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    def expect(text, start=0, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if text.encode() in output[start:]:
                return
            if process.poll() is not None:
                break
            time.sleep(.05)
        raise AssertionError(f'Missing {text!r}: {bytes(output[-3000:]).decode(errors="replace")}')
    def serial(text):
        for byte in (text + '\r\n').encode():
            process.stdin.write(bytes([byte]))
            time.sleep(.004)
    sock = None
    try:
        expect('xos64> ')
        serial('run')
        expect('xsh> ')
        serial('demo quiet')
        expect('[sup] demo tasks stopped')
        serial('interactium-start')
        expect('[interactium-service] ready')
        serial('exec-file /AURORA_DESKTOP.ELF')
        expect('[aurora] ready', timeout=120)
        expect('[qpa-frame]', timeout=120)
        sock = socket.create_connection(('127.0.0.1', port), timeout=15)
        stream = sock.makefile('rwb', buffering=0)
        json.loads(stream.readline())
        def qmp(execute, arguments=None):
            request = {'execute': execute}
            if arguments is not None:
                request['arguments'] = arguments
            stream.write(json.dumps(request).encode() + b'\n')
            while True:
                response = json.loads(stream.readline())
                if 'error' in response:
                    raise AssertionError(response)
                if 'return' in response:
                    return response['return']
        qmp('qmp_capabilities')
        def snapshot(name):
            qmp('screendump', {'filename': str(out / (name + '.ppm'))})
            image = Image.open(out / (name + '.ppm')).convert('RGB')
            image.save(out / (name + '.png'))
            return image
        def event(kind, data):
            qmp('input-send-event', {'events': [{'type': kind, 'data': data}]})
        def move(x, y):
            # Clamp against the top-left before moving to the requested point.
            # Keep each packet within PS/2's signed motion range.
            for _ in range(9):
                for axis in ('x', 'y'):
                    event('rel', {'axis': axis, 'value': -100})
                time.sleep(.04)
            for axis, distance in (('x', x), ('y', y)):
                while distance:
                    step = min(distance, 80)
                    event('rel', {'axis': axis, 'value': step})
                    distance -= step
                    time.sleep(.04)
            time.sleep(.5)
        def click(x, y):
            move(x, y)
            event('btn', {'button': 'left', 'down': True})
            time.sleep(.15)
            event('btn', {'button': 'left', 'down': False})
            time.sleep(2)
        time.sleep(2)
        baseline = snapshot('desktop')
        assert baseline.size == (800, 600)
        move(462, 570)
        time.sleep(1)
        hover = snapshot('dock_hover')
        assert hover.crop((280, 485, 520, 530)).tobytes() != baseline.crop((280, 485, 520, 530)).tobytes(), 'Dock hover name capsule'
        click(462, 570)  # examplewindow, fifth slot
        window = snapshot('window')
        assert window.getpixel((400, 350)) == (0, 0, 0), 'Dock launch'
        click(462, 570)
        minimized = snapshot('minimized')
        assert minimized.getpixel((400, 350)) == baseline.getpixel((400, 350)), 'minimize'
        click(462, 570)
        restored = snapshot('restored')
        assert restored.getpixel((400, 350)) == (0, 0, 0), 'restore'
        click(527, 152)
        maximized = snapshot('maximized')
        assert maximized.getpixel((400, 570)) == (0, 0, 0), 'maximized Dock hides'
        move(400, 599)
        time.sleep(1)
        revealed = snapshot('dock_revealed')
        assert revealed.getpixel((400, 570)) != (0, 0, 0), 'bottom edge reveals Dock'
        move(600, 300)
        time.sleep(2)
        assert snapshot('dock_hidden').getpixel((400, 570)) == (0, 0, 0), 'leave Dock hides again'
        click(765, 38)
        assert snapshot('unmaximized').getpixel((100, 300)) == baseline.getpixel((100, 300)), 'restore geometry'
        click(296, 570)  # muti
        browser = snapshot('browser')
        assert browser.getpixel((80, 140)) != restored.getpixel((80, 140)), 'browser opens'
        click(400, 52)
        for key in ('e', 'x', 'a', 'm', 'p', 'l', 'e'):
            qmp('human-monitor-command', {'command-line': 'sendkey ' + key})
            time.sleep(.15)
        time.sleep(2)
        snapshot('search')
        qmp('human-monitor-command', {'command-line': 'sendkey esc'})
        time.sleep(2)
        dismissed = snapshot('dismissed')
        assert dismissed.getpixel((400, 300)) == (0, 0, 0), 'Escape dismisses menu'
        (out / 'result.json').write_text(json.dumps({'result': 'PASS', 'checks': [
            '800x600 real XOS frame', 'Dock hover name capsule', 'Dock launch', 'minimize', 'restore',
            'maximize', 'Dock autohide / bottom-edge reveal', 'unmaximize',
            'application browser', 'keyboard search screenshot', 'Escape dismissal']}, indent=2))
        print('PASS: Aurora real QEMU mouse/keyboard and screenshots', flush=True)
    finally:
        if sock:
            sock.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        reader.join(timeout=5)


if __name__ == '__main__':
    main()
