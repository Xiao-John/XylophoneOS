# SPDX-License-Identifier: MIT AND Apache-2.0
# Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
"""Exercise actual BIOS boot, serial/keyboard input, and corrupt-stage rejection."""

import hashlib
import json
import os
from pathlib import Path
import select
import selectors
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_qemu import MACHINE, qemu_command


class QmpPipe:
    """Private local FIFOs for runners without Unix-domain sockets."""
    def __init__(self, prefix):
        self.read_fd = self.write_fd = None
        self.buffer = bytearray()
        try:
            for suffix in ('.in', '.out'):
                os.mkfifo(prefix + suffix, 0o600)
            # RDWR keeps the private endpoints open while QEMU starts. All
            # protocol I/O remains bounded even when it exits before greeting.
            self.read_fd = os.open(prefix + '.out', os.O_RDWR | os.O_NONBLOCK)
            self.write_fd = os.open(prefix + '.in', os.O_RDWR | os.O_NONBLOCK)
        except BaseException:
            self.close()
            raise

    def readline(self):
        deadline = time.monotonic() + 5
        while b'\n' not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.read_fd], [], [], remaining)[0]:
                raise TimeoutError('QMP pipe response timed out')
            data = os.read(self.read_fd, 4096)
            if not data:
                raise EOFError('QMP pipe closed')
            self.buffer.extend(data)
            if len(self.buffer) > 65536:
                raise ValueError('QMP pipe response exceeds 64 KiB')
        end = self.buffer.index(b'\n') + 1
        value = bytes(self.buffer[:end])
        del self.buffer[:end]
        return value

    def write(self, data):
        deadline = time.monotonic() + 5
        offset = 0
        while offset < len(data):
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([], [self.write_fd], [], remaining)[1]:
                raise TimeoutError('QMP pipe request timed out')
            try:
                offset += os.write(self.write_fd, data[offset:])
            except BlockingIOError:
                continue
        return offset

    def close(self):
        for name in ('read_fd', 'write_fd'):
            fd = getattr(self, name)
            if fd is not None:
                os.close(fd)
                setattr(self, name, None)


class Guest:
    def __init__(self, image, name, *, cpu="qemu64,+rdrand", debug_port=None, work_disk=None, iso=None, network=False,
                 qmp_enabled=True, network_capture=None, network_peer_port=None, log_dir=None):
        # Boot medium follows the image suffix unless the caller overrides:
        # .iso files need -cdrom, everything else (real_mode.img) stays floppy.
        if iso is None:
            iso = str(image).lower().endswith(".iso")
        self.name = name
        self.log_dir = ROOT / 'build' if log_dir is None else Path(log_dir)
        self.output = bytearray()
        self.temp = tempfile.TemporaryDirectory(prefix="xos_")
        self.qmp_path = str(Path(self.temp.name) / "qmp.sock") if qmp_enabled else None
        self.qmp_transport = os.environ.get('XOS_QMP_TRANSPORT', 'unix')
        if self.qmp_transport not in ('unix', 'pipe'):
            raise ValueError('XOS_QMP_TRANSPORT must be unix or pipe')
        self.qmp_pipe = QmpPipe(self.qmp_path) if qmp_enabled and self.qmp_transport == 'pipe' else None
        self.command = qemu_command(image, qmp=self.qmp_path, qmp_transport=self.qmp_transport,
                                    cpu=cpu, debug_port=debug_port,
                                    work_disk=work_disk, iso=iso, network=network, network_capture=network_capture,
                                    network_peer_port=network_peer_port)
        self.stderr = (self.log_dir / f'{name}_qemu.log').open('wb')
        self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=self.stderr)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.qmp_socket = None
        if self.qmp_pipe is not None:
            try:
                self.qmp('query-status')
                # Preserve the existing readiness marker used by the debugger
                # fixture, after an actual QEMU protocol round trip.
                Path(self.qmp_path).touch(exist_ok=False)
            except BaseException:
                self.close()
                raise

    def expect(self, expected, *, start=0, timeout=12):
        if expected == b"[sup] demo tasks stopped":
            alternatives = (expected, b"[xsh] demo tasks stopped")
        else:
            alternatives = (expected,)
        return self.expect_any(alternatives, start=start, timeout=timeout)

    def expect_any(self, expected_values, *, start=0, timeout=12):
        expected_values = tuple(expected_values)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            matches = [(self.output.find(expected, start), expected)
                       for expected in expected_values]
            matches = [(position, expected) for position, expected in matches if position >= 0]
            if matches:
                return min(matches)[1]
            if self.process.poll() is not None:
                raise AssertionError(f"{self.name}: QEMU exited {self.process.returncode}")
            for key, _ in self.selector.select(timeout=0.1):
                data = key.fileobj.read1(4096)
                self.output.extend(data)
        raise AssertionError(f"{self.name}: missing any of {expected_values!r}; output={self.output[-1000:]!r}")

    def expect_supervisor(self, *, trace=False, start=0, timeout=12):
        prompt = self.expect(b"xsh> ", start=start, timeout=timeout)
        if trace:
            command_start = len(self.output)
            for value in b"trace on\r":
                self.process.stdin.write(bytes([value]))
                self.process.stdin.flush()
                time.sleep(0.003)
            self.expect(b"xsh: trace on", start=command_start, timeout=timeout)
            self.expect(b"xsh> ", start=command_start, timeout=timeout)
        return prompt

    def send_line(self, data, expected):
        start = len(self.output)
        # A paced UART stream avoids overrunning the deliberately small BIOS-era FIFO.
        for value in data:
            self.process.stdin.write(bytes([value]))
            self.process.stdin.flush()
            time.sleep(0.003)
        self.expect(expected, start=start)
        self.expect(b"xos> ", start=start)

    def qmp(self, execute, arguments=None):
        if self.qmp_path is None:
            raise RuntimeError("QMP is disabled for this serial-only guest")
        if self.qmp_socket is None:
            if self.qmp_pipe is not None:
                self.qmp_socket = self.qmp_file = self.qmp_pipe
            else:
                self.qmp_socket = socket.socket(socket.AF_UNIX)
                self.qmp_socket.settimeout(5)
                self.qmp_socket.connect(self.qmp_path)
                self.qmp_file = self.qmp_socket.makefile("rwb", buffering=0)
            json.loads(self.qmp_file.readline())
            self.qmp("qmp_capabilities")
        request = {"execute": execute}
        if arguments is not None:
            request["arguments"] = arguments
        self.qmp_file.write(json.dumps(request).encode() + b"\n")
        while True:
            response = json.loads(self.qmp_file.readline())
            if "error" in response:
                raise AssertionError(response)
            if "return" in response:
                return response["return"]

    def close(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        if self.qmp_socket:
            self.qmp_file.close()
            self.qmp_socket.close()
        if self.qmp_pipe:
            self.qmp_pipe.close()
        self.selector.close()
        self.process.stdin.close()
        self.process.stdout.close()
        self.stderr.close()
        (self.log_dir / f'{self.name}_serial.log').write_bytes(self.output)
        self.temp.cleanup()


def main():
    image_path = ROOT / "build/real_mode.img"
    image = image_path.read_bytes()
    manifest = json.loads((ROOT / "build/manifest.json").read_text())
    if hashlib.sha256(image).hexdigest() != manifest["artifacts"]["real_mode.img"]["sha256"]:
        raise SystemExit("Image differs from manifest; rebuild before testing")
    results = []
    report = {
        "build_id": manifest["build_id"], "image_sha256": hashlib.sha256(image).hexdigest(),
        "machine": MACHINE, "accelerator": "tcg", "cpu": "qemu64", "memory": "512M",
        "qemu": subprocess.check_output([qemu_command(image_path)[0], "--version"],
                                        text=True).splitlines()[0],
        "checks": results, "status": "failed",
    }
    try:
        guest = Guest(image_path, "boot_smoke", cpu="qemu64")
        report["command"] = guest.command
        try:
            guest.expect(b"XOS real_mode | build " + manifest["build_id"].encode())
            guest.expect(b"xos> ")
            results.append("boot_and_build_identity")
            guest.qmp("screendump", {"filename": str(ROOT / "build/boot_screen.ppm")})
            guest.send_line(b"help\r\n", b"help  about  clear  halt")
            guest.send_line(b"about\n", b"No protected memory or user tasks yet.")
            guest.send_line(b"wat\r", b"ERROR: unknown_command")
            guest.send_line(b"helx\x08p\r", b"help  about  clear  halt")
            guest.send_line(b"aboux\x7ft\r", b"No protected memory or user tasks yet.")
            guest.send_line(b"\x08\r", b"\r\nxos> ")
            guest.send_line(b"x" * 63 + b"\r", b"ERROR: unknown_command")
            guest.send_line(b"x" * 64 + b"\r", b"ERROR: line_too_long")
            guest.send_line(b"help\r", b"help  about  clear  halt")
            results.append("serial_commands_editing_cr_lf_and_bounds")
            start = len(guest.output)
            for key in ("h", "e", "l", "p", "ret"):
                guest.qmp("human-monitor-command", {"command-line": f"sendkey {key} 20"})
                time.sleep(0.08)
            guest.expect(b"help  about  clear  halt", start=start)
            guest.expect(b"xos> ", start=start)
            results.append("bios_keyboard_command")
            guest.send_line(b"clear\r", b"Screen cleared.")
            results.append("clear_command")
            start = len(guest.output)
            for value in b"halt\r":
                guest.process.stdin.write(bytes([value]))
                guest.process.stdin.flush()
                time.sleep(0.003)
            guest.expect(b"HALTED: CPU resting; close QEMU to exit.", start=start)
            time.sleep(0.1)
            registers = guest.qmp("human-monitor-command", {"command-line": "info registers"})
            (ROOT / "build/halted_registers.log").write_text(registers)
            if "HLT=1" not in registers:
                raise AssertionError("CPU did not reach HLT")
            results.append("halt_reaches_cpu_hlt")
        finally:
            guest.close()

        with tempfile.TemporaryDirectory(prefix="xos_bad_") as folder:
            bad = bytearray(image)
            bad[514:518] = b"NOPE"
            bad_path = Path(folder) / "bad_stage.img"
            bad_path.write_bytes(bad)
            guest = Guest(bad_path, "bad_stage", cpu="qemu64")
            try:
                guest.expect(b"BOOT_ERROR: stage_two_magic")
                registers = guest.qmp("human-monitor-command", {"command-line": "info registers"})
                if "HLT=1" not in registers or b"xos> " in guest.output:
                    raise AssertionError("Corrupt stage was not safely stopped")
                results.append("corrupt_stage_rejected")
            finally:
                guest.close()
        report["status"] = "passed"
        print(f"PASS: {len(results)} checks | build {manifest['build_id']}")
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        (ROOT / "build/smoke_report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
