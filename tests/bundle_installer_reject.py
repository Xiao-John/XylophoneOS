# SPDX-License-Identifier: Apache-2.0
"""Guest installer rejects malformed names, reserved bytes and member magic."""
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from make_work_disk import create_fat32
from task_smoke import pump, send_bytes
from iso_bundle_reject import iso_file_location
import xos_bundle as xb


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    idna = ROOT / "build/idna-3.20.xpk"
    if not idna.is_file():
        raise SystemExit("missing idna xpk")
    iso_path = ROOT / "build/iso_bundle_installer_reject.iso"
    manifest = ROOT / "build/iso_bundle_installer_reject_manifest.json"
    subprocess.run([
        sys.executable, str(ROOT / "scripts/build_install_iso.py"),
        "--output", str(iso_path), "--manifest", str(manifest),
        "--member", f"4:idna.xpk={idna}",
    ], check=True, cwd=ROOT)
    base = bytearray(iso_path.read_bytes())
    extent, size = iso_file_location(base, "DASH.ELF")
    offset = extent * 2048
    good = bytes(base[offset:offset + size])
    info = xb.parse(good)
    report = {"gate": "XOSBND1 installer reject", "build_id": json.loads(
        (ROOT / "build/manifest.json").read_text())["build_id"],
        "iso_sha256": sha256(iso_path), "checks": [], "status": "failed"}

    cases = []
    name_case = bytearray(good)
    dash_index = next(i for i, m in enumerate(info["members"]) if m["type"] == xb.TYPE_DASH)
    dash = info["members"][dash_index]
    name_off = struct.unpack_from("<I", good, 64 + 64 * dash_index + 4)[0]
    name_case[64 + 64 * len(info["members"]) + name_off] = 0x5c
    cases.append(("bad-name", bytes(name_case), b"[files] bundle bad name", None))
    reserved_case = bytearray(good)
    reserved_case[32] = 1
    cases.append(("reserved1", bytes(reserved_case), b"[files] bundle reserved", None))
    magic_case = bytearray(good)
    magic_case[dash["data_off"]] = 0
    cases.append(("bad-magic", bytes(magic_case), b"[files] bundle magic rejected", None))
    # A payload that is neither a container nor an ELF must not become dash.
    legacy_case = bytearray(good)
    legacy_case[0] = ord("Y")
    cases.append(("non-elf-legacy", bytes(legacy_case), b"[files] boot payload is not ELF", "/usr/bin/dash"))
    # A bad digest on a later member must be rejected before dash is written.
    later_case = bytearray(good)
    later_case[64 + 64 * 1 + 32] ^= 0xFF
    cases.append(("later-digest", bytes(later_case),
                  b"[files] bundle digest mismatch: /var/cache/xypm/incoming/", "/usr/bin/dash"))
    # Name spans must compactly partition the name region: the second member
    # starting inside the first's bytes is rejected before anything is written.
    overlap_case = bytearray(good)
    struct.pack_into("<I", overlap_case, 64 + 64 * 1 + 4, 3)
    cases.append(("name-overlap", bytes(overlap_case),
                  b"[files] bundle names not compact", "/usr/bin/dash"))

    for label, blob, marker, absent in cases:
        image = bytearray(base)
        image[offset:offset + len(blob)] = blob
        with tempfile.TemporaryDirectory(prefix="xos_bundle_reject_") as folder:
            folder = Path(folder)
            disk = folder / "fresh.img"
            create_fat32(disk, 512)
            variant = folder / "variant.iso"
            variant.write_bytes(image)
            guest = Guest(variant, "bundle_reject_" + label, iso=True, work_disk=disk)
            try:
                guest.expect(b"xos64> ", timeout=30)
                start = len(guest.output)
                send_bytes(guest, b"run\r")
                guest.expect_supervisor(start=start, timeout=60)
                guest.expect(marker, start=start, timeout=60)
                pump(guest, 0.4)
                window = bytes(guest.output[start:])
                if b"XOSBND1 bundle processed" in window:
                    raise AssertionError(f"{label}: malformed bundle processed")
                if absent is not None:
                    begin = len(guest.output)
                    send_bytes(guest, b"stat " + absent.encode() + b"\r")
                    guest.expect(b"error=", start=begin, timeout=20)
                    pump(guest, 0.3)
                    if b"size=" in bytes(guest.output[begin:]):
                        raise AssertionError(f"{label}: {absent} was installed")
                report["checks"].append({"name": label, "passed": True})
            finally:
                guest.close()
    report["status"] = "passed"
    (ROOT / "build/iso_bundle_installer_reject_report.json").write_text(
        json.dumps(report, indent=2) + "\n")
    print("PASS: installer reject gate", [c["name"] for c in report["checks"]])


if __name__ == "__main__":
    main()
