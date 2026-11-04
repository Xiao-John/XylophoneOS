# SPDX-License-Identifier: Apache-2.0
"""Observe the live QEMU serial stream through an attached GNU Screen.

This checks a bounded screen profile; keystrokes still enter the guest probe
through its serial pipe, and the outer PTY is not a physical font renderer.
"""
import fcntl
import hashlib
import json
import os
import pty
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
import ncurses_guest_probe as guest_probe


class ScreenOutput(bytearray):
    def __init__(self, screen):
        super().__init__()
        self.screen = screen

    def extend(self, data):
        previous = len(self)
        super().extend(data)
        marker = b'W2_LOCAL_CELL'
        position = self.find(marker, max(0, previous - len(marker) + 1))
        boundary = position + len(marker) - previous if position >= 0 and self.screen.captured is None else -1
        offset = 0
        while offset < len(data):
            limit = boundary if boundary > offset else len(data)
            offset += os.write(self.screen.pipe, data[offset:limit])
            if offset == boundary:
                self.screen.captured = self.screen.capture()


class Screen:
    def __init__(self):
        if not shutil.which('screen'):
            raise RuntimeError('GNU Screen is required')
        self.temp = tempfile.TemporaryDirectory(prefix='xos-screen-')
        folder = Path(self.temp.name)
        self.fifo, self.snapshot = folder / 'serial', folder / 'screen.txt'
        os.mkfifo(self.fifo)
        self.name = 'xos_ncurses_' + str(os.getpid())
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
        env = dict(os.environ, TERM='xterm-256color', LC_ALL='en_US.UTF-8')
        def controlling_terminal():
            os.setsid()
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
        self.process = subprocess.Popen(['screen', '-U', '-S', self.name, '/bin/sh', '-c',
                                         'stty -echo; cat "$1"', '_', str(self.fifo)],
                                        stdin=slave, stdout=slave, stderr=slave, env=env,
                                        preexec_fn=controlling_terminal)
        os.close(slave)
        self.pipe = os.open(self.fifo, os.O_RDWR)
        self.stream = bytearray()
        self.captured = None
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._drain, daemon=True)
        self.thread.start()
        time.sleep(0.4)
        if self.process.poll() is not None:
            raise RuntimeError('GNU Screen failed to attach')

    def _drain(self):
        while not self.stop.is_set():
            if select.select([self.master], [], [], 0.1)[0]:
                try:
                    self.stream.extend(os.read(self.master, 4096))
                except OSError:
                    break

    def capture(self):
        for _ in range(30):
            subprocess.run(['screen', '-S', self.name, '-X', 'hardcopy', str(self.snapshot)],
                           check=True, timeout=5)
            time.sleep(0.1)
            if self.snapshot.exists() and b'W2_LOCAL_CELL' in self.snapshot.read_bytes():
                return self.snapshot.read_bytes()
        raise AssertionError('Screen did not display the local window text')

    def close(self):
        subprocess.run(['screen', '-S', self.name, '-X', 'quit'], capture_output=True, timeout=5)
        self.stop.set()
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.thread.join(timeout=2)
        os.close(self.pipe)
        os.close(self.master)
        self.temp.cleanup()


def main():
    if '--xsh' not in sys.argv or '--composed' not in sys.argv:
        raise SystemExit('screen probe requires --xsh and --composed')
    screen = Screen()
    original_guest = guest_probe.Guest
    class ScreenGuest(original_guest):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.output = ScreenOutput(screen)
    guest_probe.Guest = ScreenGuest
    try:
        guest_probe.main()
        if screen.captured is None:
            raise AssertionError('wide-screen snapshot not captured')
        if b'\xe4\xb8\xad' not in screen.stream or b'\xcc\x81' not in screen.stream:
            raise AssertionError('Screen output lacks the Chinese or combining UTF-8 bytes')
        system = Path(sys.argv[sys.argv.index('--system') + 1]).resolve()
        serial = system / 'ncurses_guest_serial.log'
        hardcopy = system / 'ncurses_screen_hardcopy.bin'
        outer = system / 'ncurses_screen_outer_pty.bin'
        hardcopy.write_bytes(screen.captured)
        outer.write_bytes(screen.stream)
        result = {'status': 'passed_subset', 'profile': 'GNU Screen attached 24x80, xterm serial subset',
                  'screen_version': subprocess.run(['screen', '-v'], capture_output=True, text=True).stdout.strip(),
                  'screen_binary_sha256': hashlib.sha256(Path(shutil.which('screen')).read_bytes()).hexdigest(),
                  'probe_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'guest_report_sha256': hashlib.sha256((system / 'ncurses_guest_probe_report.json').read_bytes()).hexdigest(),
                  'serial_sha256': hashlib.sha256(serial.read_bytes()).hexdigest(),
                  'hardcopy_sha256': hashlib.sha256(hardcopy.read_bytes()).hexdigest(),
                  'outer_pty_sha256': hashlib.sha256(outer.read_bytes()).hexdigest(),
                  'checks': ['screen_window_ascii_hardcopy', 'screen_outer_pty_cjk_and_combining_bytes'],
                  'not_run': ['physical_font_rendering', 'host_keyboard_translation', 'all_xterm_capabilities']}
        (system / 'ncurses_screen_report.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
    finally:
        screen.close()


if __name__ == '__main__':
    main()
