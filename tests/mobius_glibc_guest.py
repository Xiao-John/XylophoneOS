#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify the real glibc Mobius preview and session on a dedicated XOS work disk."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from boot_smoke import Guest
from desktop_product_packages import press
from graphics_guest import start_graphics, stop_graphics
from make_work_disk import create_fat32
from process_smoke import resources
from task_smoke import pump, send_bytes
from work_disk import transfer


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def scanout(guest, path, light):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        guest.qmp("screendump", {"filename": str(path)})
        kind, geometry, depth, pixels = path.read_bytes().split(b"\n", 3)
        assert kind == b"P6" and geometry == b"800 600" and depth == b"255"
        assert len(pixels) == 800 * 600 * 3
        colors = {pixels[i:i + 3] for i in range(0, len(pixels), 3)}
        bright = sum(min(pixels[i:i + 3]) > 170 for i in range(0, len(pixels), 3))
        if len(colors) > 100 and (bright > 100000) == light:
            return {"sha256": sha(path), "colors": len(colors), "bright_pixels": bright}
        pump(guest, 0.12)
    raise AssertionError(f"Mobius {path.stem} did not reach scanout")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("system", "target", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--work-disk-tool", type=Path, help="prebuilt native XOS FAT helper")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True)
    system = args.system.resolve(strict=True)
    image = system / "xos-install.iso"
    manifest = system / "manifest.json"
    metadata = json.loads(manifest.read_text())
    assert sha(image) == metadata["artifacts"]["xos-install.iso"]["sha256"]
    desktop = (args.target / "mobius.elf").resolve(strict=True)
    session = (args.target / "mobius_session.elf").resolve(strict=True)
    report = {"status": "FAILED", "system_build_id": metadata["build_id"],
              "system_manifest_sha256": sha(manifest), "image_sha256": sha(image), "elfs": {}}
    for path in (desktop, session):
        receipt_path = path.with_suffix(".receipt.json")
        receipt = json.loads(receipt_path.read_text())
        assert sha(path) == receipt["elf_sha256"]
        report["elfs"][path.name] = {"sha256": receipt["elf_sha256"],
                                    "sdk_manifest_sha256": receipt["sdk_manifest_sha256"],
                                    "build_receipt_sha256": sha(receipt_path)}

    try:
        with tempfile.TemporaryDirectory(prefix="xos_mobius_glibc_") as temp:
            disk = Path(temp) / "work.img"
            create_fat32(disk, 512)
            for operation in (("mkdir", "/usr"), ("mkdir", "/usr/bin"),
                              ("import", "/usr/bin/mobius.elf", desktop),
                              ("import", "/usr/bin/mobius-session.elf", session)):
                if args.work_disk_tool:
                    subprocess.run([args.work_disk_tool.resolve(), disk, *operation], check=True)
                else:
                    transfer(disk, *operation)
            guest = Guest(image, "mobius", work_disk=disk, log_dir=output)
            try:
                report["qemu_version"] = subprocess.check_output(
                    [guest.command[0], "--version"], text=True).splitlines()[0]
                guest.expect(b"xos64> ", timeout=40)
                send_bytes(guest, b"run\r")
                guest.expect_supervisor(trace=True, timeout=40)
                pump(guest, 1.5)
                report["baseline"] = resources(guest)
                graphics = start_graphics(guest)
                report["with_graphics"] = resources(guest)
                report["launches"] = []

                for launcher, entry in (("preview", "exec-file /usr/bin/mobius.elf"),
                                        ("session", "exec-driver /usr/bin/mobius-session.elf")):
                    begin = len(guest.output)
                    started = time.monotonic()
                    send_bytes(guest, entry.encode() + b"\r")
                    # The glibc parent reads the desktop through its bounded, polling file session.
                    guest.expect(b"DESKTOP_READY", start=begin, timeout=360 if launcher == "session" else 90)
                    ready_seconds = round(time.monotonic() - started, 3)
                    guest.expect(b"[qpa-frame]", start=begin, timeout=30)
                    dark = scanout(guest, output / f"{launcher}_midnight.ppm", light=False)
                    begin_appearance = len(guest.output)
                    press(guest, "comma", "ctrl")
                    guest.expect(b"DESKTOP_PAGE index=3", start=begin_appearance)
                    begin_theme = len(guest.output)
                    press(guest, "d", "ctrl")
                    guest.expect(b'"scheme":"daybreak"', start=begin_theme)
                    light = scanout(guest, output / f"{launcher}_daybreak.ppm", light=True)
                    assert light["sha256"] != dark["sha256"]
                    press(guest, "q", "ctrl")
                    guest.expect(b"kind=exited code=0", start=begin, timeout=30)
                    guest.expect_supervisor(start=begin)
                    serial = bytes(guest.output)[begin:]
                    pid = re.search(rb"\[loader\] started pid=(\d+)", serial)[1]
                    assert b"[wait] pid=" + pid + b" kind=exited code=0" in serial
                    assert b"input-thread-joined" in serial
                    sample = re.search(rb"DESKTOP_SAMPLE pages=(\d+) threads=(\d+) startup_ms=(\d+)", serial)
                    assert sample is not None
                    after = resources(guest)
                    assert after == report["with_graphics"]
                    report["launches"].append({"launcher": launcher, "ready_wall_seconds": ready_seconds,
                                               "midnight": dark, "daybreak": light,
                                               "desktop_sample": [int(number) for number in sample.groups()],
                                               "after_payload": after})
                stop_graphics(guest, *graphics)
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
