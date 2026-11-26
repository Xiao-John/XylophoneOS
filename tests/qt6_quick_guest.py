#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the real XOS Qt Quick software scene, input, and scanout."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
import boot_smoke
from graphics_guest import start_graphics, stop_graphics
from make_work_disk import create_fat32
from process_smoke import resources
from task_smoke import pump, send_bytes
from work_disk import transfer


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def scanout(guest, capture, color, previous_x=None):
    """Locate a complete rectangular bar and light glyphs in QEMU's P6 scanout."""
    deadline = time.monotonic() + 5
    background = bytes.fromhex("17354d")
    color = bytes.fromhex(color)
    while time.monotonic() < deadline:
        guest.qmp("screendump", {"filename": str(capture)})
        kind, geometry, depth, pixels = capture.read_bytes().split(b"\n", 3)
        width, height = map(int, geometry.split())
        assert kind == b"P6" and depth == b"255" and len(pixels) == width * height * 3
        # The fixture places the window at (32, 40), away from the cursor.
        def row(x, y, count):
            begin = (y * width + x) * 3
            return pixels[begin:begin + count * 3]

        y = 40 + 112
        bar = color * 140
        bar_x = next((x for x in range(50, 163, 16) if row(x, y, 140) == bar), None)
        if (bar_x is not None and bar_x != previous_x
                and row(bar_x, y + 39, 140) == bar and row(32, 40, 1) == background):
            ink = 0
            for text_y in range(62, 105):
                text = row(50, text_y, 300)
                ink += sum(min(text[i:i + 3]) > 200 for i in range(0, len(text), 3))
            assert ink > 100, ink
            return {"bar_x": bar_x, "text_ink_pixels": ink, "screenshot_sha256": digest(capture)}
        pump(guest, 0.12)
    raise AssertionError(f"Expected Quick scanout pixels did not reach QEMU: {capture.name}")


def stroke(guest, key):
    for down in (True, False):
        guest.qmp("input-send-event", {"events": [{"type": "key", "data": {
            "down": down, "key": {"type": "qcode", "data": key}}}]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory")
    parser.add_argument("--work-disk-tool", type=Path, help="prebuilt native XOS FAT helper")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True)
    report = {"status": "FAILED", "image_sha256": digest(args.image),
              "elf_sha256": digest(args.payload), "cycles": []}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix="xos_qt_quick_") as temp:
            disk = Path(temp) / "work.img"
            create_fat32(disk, 512)
            for operation in (("mkdir", "/bin"), ("import", "/bin/quick.elf", args.payload.resolve())):
                if args.work_disk_tool:
                    subprocess.run([args.work_disk_tool.resolve(), disk, *operation], check=True)
                else:
                    transfer(disk, *operation)
            # Route the existing guest helper's logs alongside this receipt.
            (output / "build").mkdir()
            with patch.object(boot_smoke, "ROOT", output):
                guest = boot_smoke.Guest(args.image.resolve(), "guest", work_disk=disk)
                try:
                    report["qemu_command"] = guest.command
                    report["qemu_version"] = subprocess.check_output(
                        [guest.command[0], "--version"], text=True).splitlines()[0]
                    guest.expect(b"xos64> ", timeout=40)
                    send_bytes(guest, b"run\r")
                    guest.expect_supervisor(trace=True, timeout=30)
                    pump(guest, 1.5)
                    report["baseline"] = resources(guest)
                    display, compositor = start_graphics(guest)
                    report["with_graphics"] = resources(guest)
                    begin = len(guest.output)
                    send_bytes(guest, b"exec-file /bin/quick.elf\r")
                    for cycle in (1, 2):
                        guest.expect(f"QT_QUICK_FRAME cycle={cycle}".encode(), start=begin, timeout=60)
                        first = scanout(guest, output / f"cycle_{cycle}_start.ppm", "35c29d")
                        moved = scanout(guest, output / f"cycle_{cycle}_moved.ppm", "35c29d", first["bar_x"])
                        stroke(guest, "a")
                        guest.expect(f"QT_QUICK_KEY cycle={cycle}".encode(), start=begin)
                        keyed = scanout(guest, output / f"cycle_{cycle}_key.ppm", "f0a945")
                        stroke(guest, "b")
                        guest.expect(f"QT_QUICK_SCENE_OK cycle={cycle}".encode(), start=begin)
                        report["cycles"].append({"cycle": cycle, "start": first, "moved": moved, "key": keyed})
                    guest.expect(b"QT_QUICK_SMOKE_OK", start=begin)
                    guest.expect(b"kind=exited code=0", start=begin)
                    guest.expect_supervisor(start=begin)
                    serial = bytes(guest.output)[begin:]
                    frames = re.findall(rb"\[qpa-frame\] rects=\d+ stride=\d+ ns=(\d+)", serial)
                    samples = re.findall(rb"QT_QUICK_SCENE_OK cycle=(\d+) frames=(\d+) "
                                         rb"sampled_peak_pages=(\d+) max_frame_interval_ns=(\d+)", serial)
                    assert len(frames) >= 4 and len(samples) == 2
                    assert serial.count(b"input-thread-joined") == 2
                    report["frame_flush_ns"] = [int(frame) for frame in frames]
                    report["scene_samples"] = [tuple(map(int, sample)) for sample in samples]
                    report["after_payload"] = resources(guest)
                    assert report["after_payload"] == report["with_graphics"]
                    stop_graphics(guest, display, compositor)
                    report["after_services"] = resources(guest)
                    assert report["after_services"] == report["baseline"]
                    report["status"] = "PASSED"
                finally:
                    guest.close()
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
