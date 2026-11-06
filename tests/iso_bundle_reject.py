# SPDX-License-Identifier: Apache-2.0
"""XOSBND1 reject gate: host parse must reject four bad containers, and a
bad-sha container booted as DASH.ELF must not install as /usr/bin/dash."""
import argparse
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
import xos_bundle as xb
from boot_smoke import Guest
from install_dash import latest_manifest, project_root
from make_work_disk import create_fat32
from task_smoke import pump, send_bytes


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def load_dash_elf():
    manifest = latest_manifest()
    data = json.loads(manifest.read_text())
    elf = (project_root(manifest) / data["elf"]).resolve(strict=True)
    digest = hashlib.sha256(elf.read_bytes()).hexdigest()
    if digest != data["sha256"]:
        raise SystemExit("dash ELF does not match its manifest")
    return elf.read_bytes()


def expect_bundle_error(blob, label, checks):
    try:
        xb.parse(blob)
    except xb.BundleError as exc:
        checks.append({"name": label, "passed": True, "error": str(exc)})
        return
    raise AssertionError(f"{label}: parse accepted bad container")


def host_checks(dash_elf, xpk, checks):
    good = xb.build([(xb.TYPE_DASH, "dash", dash_elf),
                     (xb.TYPE_AUX, "idna.xpk", xpk)])
    info = xb.parse(good)
    checks.append({"name": "good-container-accepted", "passed": True,
                   "members": [m["name"] for m in info["members"]]})

    bad_magic = bytearray(good)
    bad_magic[0:8] = b"NOTABND\x00"
    expect_bundle_error(bytes(bad_magic), "reject-bad-magic", checks)

    dash_member = info["members"][0]
    bad_sha = bytearray(good)
    at = dash_member["data_off"] + dash_member["data_len"] // 2
    bad_sha[at] ^= 0xFF
    expect_bundle_error(bytes(bad_sha), "reject-bad-sha", checks)

    truncated = good[:len(good) // 2]
    expect_bundle_error(truncated, "reject-truncated", checks)

    try:
        xb.build([(xb.TYPE_DASH, "dash", dash_elf),
                  (xb.TYPE_DASH, "dash2", dash_elf)])
    except xb.BundleError as exc:
        checks.append({"name": "reject-double-dash-build", "passed": True,
                       "error": str(exc)})
    else:
        raise AssertionError("build accepted two dash members")

    double_dash = bytearray(good)
    struct.pack_into("<I", double_dash, xb.HEADER_SIZE + xb.ENTRY_SIZE,
                     xb.TYPE_DASH)
    expect_bundle_error(bytes(double_dash), "reject-double-dash-parse", checks)
    return good


def iso_file_location(image, name):
    pvd = image[16 * 2048:17 * 2048]
    root_lba = int.from_bytes(pvd[156 + 2:156 + 6], "little")
    root_size = int.from_bytes(pvd[156 + 10:156 + 14], "little")
    for sector in range((root_size + 2047) // 2048):
        block = image[(root_lba + sector) * 2048:(root_lba + sector + 1) * 2048]
        offset = 0
        while offset < 2048:
            length = block[offset]
            if length == 0:
                break
            name_len = block[offset + 32]
            raw = block[offset + 33:offset + 33 + name_len].decode("ascii")
            if raw not in (".", "..", "\x00", "\x01"):
                fname = raw.split(";")[0]
                extent = int.from_bytes(block[offset + 2:offset + 6], "little")
                size = int.from_bytes(block[offset + 10:offset + 14], "little")
                if fname == name:
                    return extent, size
            offset += length
    raise AssertionError(f"{name} not found in ISO root")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path,
                        default=ROOT / "build/iso_bundle_reject_report.json")
    parser.add_argument("--idna", type=Path, default=ROOT / "build/idna-3.20.xpk")
    args = parser.parse_args()
    if not args.idna.is_file():
        raise SystemExit(f"missing idna xpk: {args.idna}")

    system = json.loads((ROOT / "build/manifest.json").read_text())
    report = {"gate": "XOSBND1 bundle reject", "build_id": system["build_id"],
              "checks": [], "status": "failed"}

    dash_elf = load_dash_elf()
    xpk = args.idna.read_bytes()
    good = host_checks(dash_elf, xpk, report["checks"])

    iso = ROOT / "build/iso_bundle_reject.iso"
    manifest = ROOT / "build/iso_bundle_reject_manifest.json"
    subprocess.run([
        sys.executable, str(ROOT / "scripts/build_install_iso.py"),
        "--output", str(iso),
        "--manifest", str(manifest),
        "--member", f"4:idna.xpk={args.idna}",
    ], check=True, cwd=ROOT)
    bundle_meta = json.loads(manifest.read_text())
    report["bundle"] = bundle_meta.get("boot_bundle")
    report["iso_sha256"] = hashlib.sha256(iso.read_bytes()).hexdigest()

    # Corrupt the dash member sha inside the ISO's DASH.ELF (guest bad-sha case).
    image = bytearray(iso.read_bytes())
    extent, size = iso_file_location(image, "DASH.ELF")
    if size != len(good):
        raise AssertionError(f"DASH.ELF size {size} != bundle {len(good)}")
    off = extent * 2048
    if image[off:off + size] != good:
        raise AssertionError("ISO DASH.ELF does not match generated bundle")
    image[off + xb.HEADER_SIZE + 32] ^= 0xFF
    bad_container = bytes(image[off:off + size])
    try:
        xb.parse(bad_container)
    except xb.BundleError as exc:
        if "sha256" not in str(exc):
            raise AssertionError(f"unexpected host reject: {exc}")
        report["checks"].append({"name": "bad-iso-container-rejected-host",
                                 "passed": True, "error": str(exc)})
    else:
        raise AssertionError("corrupted ISO container still parses")
    bad_iso = ROOT / "build/iso_bundle_reject_bad.iso"
    bad_iso.write_bytes(image)

    report["bad_iso_sha256"] = hashlib.sha256(image).hexdigest()
    with tempfile.TemporaryDirectory(prefix="xos_bundle_reject_") as folder:
        disk = Path(folder) / "fresh.img"
        create_fat32(disk, 512)
        guest = Guest(bad_iso, "iso_bundle_reject", iso=True, work_disk=disk)
        try:
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(start=start, timeout=60)
            guest.expect(b"[files] bundle digest mismatch: /usr/bin/dash",
                         start=start, timeout=30)
            report["checks"].append({"name": "guest-digest-rejected",
                                     "passed": True})
            pump(guest, 0.5)
            window = bytes(guest.output[start:])
            for forbidden in (b"dash installed bytes=",
                              b"[files] bundle installed:",
                              b"XOSBND1 bundle processed"):
                if forbidden in window:
                    raise AssertionError(
                        f"bad container took success path: {forbidden!r}")
            report["checks"].append({"name": "no-success-install-path",
                                     "passed": True})
            begin = len(guest.output)
            send_bytes(guest, b"type dash\r")
            guest.expect_any((b"not found", b"not executable"),
                             start=begin, timeout=20)
            pump(guest, 0.3)
            type_window = bytes(guest.output[begin:])
            if b"dash -> " in type_window:
                raise AssertionError("type dash resolved a bad install")
            report["checks"].append({"name": "dash-not-resolvable",
                                     "passed": True})
            begin = len(guest.output)
            send_bytes(guest, b"dash -i\r")
            guest.expect_any((b"not found", b"not executable"),
                             start=begin, timeout=20)
            pump(guest, 0.3)
            if b"$ " in bytes(guest.output[begin:]):
                raise AssertionError("bad container bytes ran as dash")
            report["checks"].append({"name": "dash-not-runnable",
                                     "passed": True})
            report["status"] = "passed"
        except Exception as exc:
            report["error"] = str(exc)
            report["output_tail"] = bytes(guest.output[-4000:]).decode(
                errors="replace")
            raise
        finally:
            guest.close()
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"],
                      "checks": report["checks"]}, indent=2))


if __name__ == "__main__":
    main()
