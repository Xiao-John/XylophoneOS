# SPDX-License-Identifier: Apache-2.0
"""Boot the real XOS guest and verify the Interactium two-window display."""
import os
import json
from pathlib import Path
import re
import socket
import sys
import subprocess
import tempfile
import struct
import zlib
import argparse
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "scripts")]
from boot_smoke import Guest
from task_smoke import send_bytes, pump
import boot_smoke
from run_qemu import qemu_command as original_qemu_command
from make_work_disk import create_fat32


def qmp_command(guest, execute, arguments=None):
    request = {"execute": execute}
    if arguments is not None:
        request["arguments"] = arguments
    guest.qmp_file.write(json.dumps(request).encode() + b"\n")
    while True:
        response = json.loads(guest.qmp_file.readline())
        if "error" in response:
            raise AssertionError(response)
        if "return" in response:
            return response["return"]


def write_png(path, pixels, width, height):
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xffffffff)
    rows = b"".join(b"\0" + pixels[y * width * 3:(y + 1) * width * 3]
                    for y in range(height))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" +
                     chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
                     chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=ROOT / "build/xos-install.iso")
    image = parser.parse_args().image.resolve()
    if not image.is_file():
        raise SystemExit(f"{image} missing; run scripts/build.py first")
    os.environ.setdefault("QEMU", str(Path("C:/msys64/ucrt64/bin/qemu-system-x86_64.exe")))
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        qmp_port = reservation.getsockname()[1]
    def qemu_tcp(*args, **kwargs):
        kwargs["qmp"] = None
        command = original_qemu_command(*args, **kwargs)
        command += ["-qmp", f"tcp:127.0.0.1:{qmp_port},server=on,wait=off"]
        return command
    with patch.object(boot_smoke, "qemu_command", qemu_tcp):
        disk_fd, disk_name = tempfile.mkstemp(prefix="xos_interactium_", suffix=".img")
        os.close(disk_fd)
        work_disk = Path(disk_name)
        work_disk.unlink()
        create_fat32(work_disk, 512)
        guest = Guest(image, "interactium_guest", work_disk=work_disk, iso=True)
    try:
        guest.expect(b"xos64> ", timeout=45)
        start = len(guest.output)
        send_bytes(guest, b"run\r\n")
        guest.expect_any((b"sup> ", b"xsh> "), start=start, timeout=15)
        guest.expect(b"[input] ps2=ready", start=start, timeout=15)

        start = len(guest.output)
        send_bytes(guest, b"exec ipc_probe\r\n")
        try:
            guest.expect(b"IPC_ENDPOINT_PASS", start=start, timeout=15)
        except AssertionError as error:
            raise AssertionError(bytes(guest.output[start:]).decode("utf-8", "replace")) from error
        guest.expect_any((b"sup> ", b"xsh> "), start=start, timeout=15)

        start = len(guest.output)
        send_bytes(guest, b"demo quiet\r\n")
        guest.expect(b"[sup] demo tasks stopped", start=start, timeout=15)
        guest.expect_any((b"sup> ", b"xsh> "), start=start, timeout=15)

        start = len(guest.output)
        send_bytes(guest, b"interactium-start\r\n")
        guest.expect(b"[interactium-service] ready", start=start, timeout=15)
        guest.expect_any((b"sup> ", b"xsh> "), start=start, timeout=15)
        service_output = bytes(guest.output[start:])
        service_match = re.search(rb"\[interactium-start\] pid=(\d+)", service_output)
        assert service_match is not None, service_output.decode("utf-8", "replace")
        service_pid = int(service_match.group(1))

        for _ in range(2):
            start = len(guest.output)
            send_bytes(guest, b"exec ic_client\r\n")
            guest.expect(b"INTERACTIUM_CLIENT_PASS", start=start, timeout=20)
            guest.expect_any((b"sup> ", b"xsh> "), start=start, timeout=20)
        start = len(guest.output)
        send_bytes(guest, f"kill {service_pid}\r\n".encode())
        guest.expect(b"kill: accepted", start=start, timeout=15)
        guest.expect_any((b"sup> ", b"xsh> "), start=start, timeout=15)
        start = len(guest.output)
        send_bytes(guest, b"exec ic_client\r\n")
        guest.expect(b"xsh: program exited with status 20", start=start, timeout=15)
        guest.expect_any((b"sup> ", b"xsh> "), start=start, timeout=15)

        start = len(guest.output)
        send_bytes(guest, b"exec interactium\r\n")
        guest.expect(b"[interactium-demo] two windows visible", start=start, timeout=20)
        pump(guest, 0.5)
        screenshot = ROOT / "build/interactium_demo.png"
        ppm = ROOT / "build/interactium_demo.ppm"
        guest.qmp_socket = socket.create_connection(("127.0.0.1", qmp_port), timeout=5)
        guest.qmp_file = guest.qmp_socket.makefile("rwb", buffering=0)
        json.loads(guest.qmp_file.readline())
        qmp_command(guest, "qmp_capabilities")
        ppm_for_qemu = subprocess.check_output(["cygpath", "-w", str(ppm)], text=True).strip()
        qmp_command(guest, "screendump", {"filename": ppm_for_qemu})
        ppm_bytes = ppm.read_bytes()
        ppm_header = b"P6\n800 600\n255\n"
        assert ppm_bytes.startswith(ppm_header) and len(ppm_bytes) == len(ppm_header) + 800 * 600 * 3
        pixels = ppm_bytes[len(ppm_header):]
        def pixel(x, y):
            offset = (y * 800 + x) * 3
            return tuple(pixels[offset:offset + 3])
        assert pixel(400, 300) == (0x10, 0x18, 0x20)
        assert pixel(401, 304) == (0xf5, 0xf7, 0xfa)
        assert pixel(80, 100) == (0x3e, 0x82, 0x90)
        assert pixel(370, 240) == (0xd2, 0x8b, 0x3c)
        write_png(screenshot, pixels, 800, 600)

        for event in (
            {"type": "rel", "data": {"axis": "x", "value": -300}},
            {"type": "rel", "data": {"axis": "y", "value": -190}},
            {"type": "btn", "data": {"down": True, "button": "left"}},
            {"type": "rel", "data": {"axis": "x", "value": 80}},
            {"type": "rel", "data": {"axis": "y", "value": 50}},
            {"type": "btn", "data": {"down": False, "button": "left"}},
        ):
            qmp_command(guest, "input-send-event", {"events": [event]})
            pump(guest, 0.12)
        dragged_ppm = ROOT / "build/interactium_demo_dragged.ppm"
        dragged_png = ROOT / "build/interactium_demo_dragged.png"
        dragged_ppm_for_qemu = subprocess.check_output(["cygpath", "-w", str(dragged_ppm)], text=True).strip()
        qmp_command(guest, "screendump", {"filename": dragged_ppm_for_qemu})
        dragged = dragged_ppm.read_bytes()[len(ppm_header):]
        def dragged_pixel(x, y):
            offset = (y * 800 + x) * 3
            return tuple(dragged[offset:offset + 3])
        assert dragged_pixel(160, 150) == (0x3e, 0x82, 0x90)
        assert dragged_pixel(370, 240) == (0x18, 0x21, 0x2d)
        write_png(dragged_png, dragged, 800, 600)

        qmp_command(guest, "input-send-event", {"events": [
            {"type": "key", "data": {"down": True, "key": {"type": "qcode", "data": "q"}}},
            {"type": "key", "data": {"down": False, "key": {"type": "qcode", "data": "q"}}},
        ]})
        guest.expect(b"[interactium-demo] closed", start=start, timeout=15)
        guest.expect_any((b"sup> ", b"xsh> "), start=start, timeout=15)
        print(f"Interactium guest passed; screenshot={screenshot}")
    finally:
        guest.close()
        work_disk.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
