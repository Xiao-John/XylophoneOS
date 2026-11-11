# SPDX-License-Identifier: Apache-2.0
"""A different bundle on the same disk must not be skipped by the marker."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from make_work_disk import create_fat32
from task_smoke import pump, send_bytes
from dash_b2_smoke import build_probe


def build_iso(output, manifest, members):
    command = [sys.executable, str(ROOT / "scripts/build_install_iso.py"),
               "--output", str(output), "--manifest", str(manifest)]
    for member in members:
        command += ["--member", member]
    subprocess.run(command, check=True, cwd=ROOT)


def main():
    idna = ROOT / "build/idna-3.20.xpk"
    daily = ROOT / "build/daily_utils_002.xpk"
    if not idna.is_file() or not daily.is_file():
        raise SystemExit("missing idna/daily xpk")
    with tempfile.TemporaryDirectory(prefix="xos_bundle_marker_") as folder:
        folder = Path(folder)
        fake = folder / "xypm"
        build_probe(ROOT / "tests/fixtures/fake_xypm.c", fake, ROOT / "build/sdk")
        iso_a, iso_b = folder / "a.iso", folder / "b.iso"
        build_iso(iso_a, folder / "a.json", [f"5:xypm={fake}", f"4:idna.xpk={idna}"])
        build_iso(iso_b, folder / "b.json", [f"5:xypm={fake}", f"3:daily={daily}"])
        disk = folder / "work.img"
        create_fat32(disk, 512)

        first = Guest(iso_a, "bundle_marker_a", iso=True, work_disk=disk)
        try:
            first.expect(b"xos64> ", timeout=30)
            start = len(first.output)
            send_bytes(first, b"run\r")
            first.expect_supervisor(start=start, timeout=120)
            first.expect(b"[files] bundle packages installed", start=start, timeout=300)
            begin = len(first.output)
            send_bytes(first, b"cat /var/cache/xypm/du4_bundle.installed\r")
            first.expect(b"xsh> ", start=begin, timeout=30)
            marker_a = bytes(first.output[begin:])
        finally:
            first.close()

        second = Guest(iso_b, "bundle_marker_b", iso=True, work_disk=disk)
        try:
            second.expect(b"xos64> ", timeout=30)
            start = len(second.output)
            send_bytes(second, b"run\r")
            second.expect_supervisor(start=start, timeout=180)
            # Different payload identity: the new bundle must be processed and
            # the marker must be rewritten for bundles B's payload.
            second.expect(b"[files] XOSBND1 bundle processed members=", start=start, timeout=300)
            second.expect(b"[files] bundle packages installed", start=start, timeout=300)
            begin = len(second.output)
            send_bytes(second, b"cat /var/cache/xypm/du4_bundle.installed\r")
            second.expect(b"xsh> ", start=begin, timeout=30)
            marker_b = bytes(second.output[begin:])
            if marker_a == marker_b:
                raise AssertionError("marker digest did not change for a new bundle")
            window = bytes(second.output[start:])
            if b"bundle package install incomplete" in window:
                raise AssertionError("new bundle failed to install")
        finally:
            second.close()
    print("PASS: bundle marker identity")


if __name__ == "__main__":
    main()
