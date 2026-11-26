#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify the external Qt Quick kit example on a real XOS image."""

import argparse
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
from graphics_guest import start_graphics, stop_graphics
from make_work_disk import create_fat32
from process_smoke import command, resources
from qt6_quick_guest import digest
from task_smoke import pump, send_bytes
from work_disk import transfer
from xypm_sdk_profile import relative_file


def capture_external_scene(guest, capture):
    deadline = time.monotonic() + 5
    partial_captures = 0
    highest_partial_ink = 0
    while time.monotonic() < deadline:
        guest.qmp("screendump", {"filename": str(capture)})
        kind, geometry, depth, pixels = capture.read_bytes().split(b"\n", 3)
        width, height = map(int, geometry.split())
        assert kind == b"P6" and depth == b"255" and len(pixels) == width * height * 3
        point = (41 * width + 33) * 3
        if pixels[point:point + 3] == bytes.fromhex("183c38"):
            ink = 0
            for y in range(85, 145):
                point = (y * width + 55) * 3
                row = pixels[point:point + 200 * 3]
                ink += sum(min(row[x:x + 3]) > 200 for x in range(0, len(row), 3))
            if ink > 100:
                return {"mode": [width, height], "text_ink_pixels": ink, "sha256": digest(capture),
                        "partial_captures": partial_captures}
            # QMP can read scanout while the compositor is still copying the window.
            partial_captures += 1
            highest_partial_ink = max(highest_partial_ink, ink)
        pump(guest, 0.12)
    raise AssertionError(f"The external Qt Quick scene did not reach scanout. "
                         f"Partial captures: {partial_captures}, highest text ink: {highest_partial_ink}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("system", "receipt", "kit-manifest", "output"):
        parser.add_argument(f"--{field}", type=Path, required=True)
    parser.add_argument("--dash-manifest", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True)
    system_manifest = args.system / "manifest.json"
    system = json.loads(system_manifest.read_text())
    image = args.system / "xos-install.iso"
    app = json.loads(args.receipt.read_text())
    payload = relative_file(args.receipt.parent, app["elf"])
    report = {
        "status": "failed",
        "launcher": "xsh",
        "system_build_id": system["build_id"],
        "system_manifest_sha256": digest(system_manifest),
        "image_sha256": digest(image),
        "elf_sha256": digest(payload),
        "app_receipt_sha256": digest(args.receipt),
        "kit_manifest_sha256": digest(args.kit_manifest),
    }
    try:
        assert report["image_sha256"] == system["artifacts"]["xos-install.iso"]["sha256"]
        assert report["elf_sha256"] == app["elf_sha256"]
        assert report["kit_manifest_sha256"] == app["kit_manifest_sha256"]
        assert app["status"] == "static_quick_application_linked"
        operations = [("mkdir", "/bin"), ("import", "/bin/quick.elf", payload)]
        launch = "exec-file /bin/quick.elf"
        if args.dash_manifest:
            dash = json.loads(args.dash_manifest.read_text())
            dash_elf = ROOT / dash["elf"]
            assert dash["profile"] == "dash_c3"
            assert dash["sdk_manifest_sha256"] == system["artifacts"]["sdk/manifest.json"]["sha256"]
            assert digest(dash_elf) == dash["sha256"]
            operations += [("mkdir", "/usr"), ("mkdir", "/usr/bin"), ("import", "/usr/bin/dash", dash_elf)]
            launch = "dash -c /bin/quick.elf"
            report.update(launcher="dash", dash_manifest_sha256=digest(args.dash_manifest),
                          dash_elf_sha256=dash["sha256"])
        with tempfile.TemporaryDirectory(prefix="xos_quick_kit_") as temp:
            disk = Path(temp) / "work.img"
            create_fat32(disk, 512)
            for operation in operations:
                transfer(disk, *operation)
            guest = Guest(image.resolve(), "guest", work_disk=disk, log_dir=output)
            try:
                report["qemu_version"] = subprocess.check_output(
                    [guest.command[0], "--version"], text=True).splitlines()[0]
                guest.expect(b"xos64> ", timeout=40)
                send_bytes(guest, b"run\r")
                guest.expect_supervisor(trace=True, timeout=30)
                pump(guest, 1.5)
                if args.dash_manifest:
                    command(guest, "type dash", b"dash -> /usr/bin/dash")
                report["baseline"] = resources(guest)
                display, compositor = start_graphics(guest)
                report["with_graphics"] = resources(guest)
                begin = len(guest.output)
                send_bytes(guest, launch.encode() + b"\r")
                guest.expect(b"QT_QUICK_EXTERNAL_FRAME", start=begin, timeout=60)
                report["scanout"] = capture_external_scene(guest, output / "scanout.ppm")
                start_line = guest.output[begin:]
                launcher_pid = re.search(rb"\[loader\] started pid=(\d+)", start_line)[1]
                guest.expect(b"[wait] pid=" + launcher_pid + b" kind=exited code=0", start=begin)
                guest.expect_supervisor(start=begin)
                serial = guest.output[begin:]
                assert b"input-thread-joined" in serial and b"[qpa-frame]" in serial
                report["after_payload"] = resources(guest)
                assert report["after_payload"] == report["with_graphics"]
                stop_graphics(guest, display, compositor)
                report["after_services"] = resources(guest)
                assert report["after_services"] == report["baseline"]
                report["status"] = "passed_subset"
            finally:
                guest.close()
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
