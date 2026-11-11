# SPDX-License-Identifier: Apache-2.0
"""DU4: boot an XOSBND1 install ISO, extract members, stage XPK for xypm."""
import argparse
import hashlib
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


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "build/iso_bundle_install_report.json")
    parser.add_argument("--idna", type=Path, default=ROOT / "build/idna-3.20.xpk")
    args = parser.parse_args()
    if not args.idna.is_file():
        raise SystemExit(f"missing idna xpk: {args.idna}")

    iso = ROOT / "build/xos-install-bundle.iso"
    manifest = ROOT / "build/install_bundle_manifest.json"
    subprocess.run([
        sys.executable, str(ROOT / "scripts/build_install_iso.py"),
        "--output", str(iso),
        "--manifest", str(manifest),
        "--member", f"4:idna.xpk={args.idna}",
    ], check=True, cwd=ROOT)
    bundle_meta = json.loads(manifest.read_text())
    members = bundle_meta.get("boot_bundle", {}).get("members", [])
    if len(members) < 2:
        raise SystemExit(f"expected dash+idna in bundle metadata, got {members}")

    system = json.loads((ROOT / "build/manifest.json").read_text())
    report = {
        "gate": "DU4 XOSBND1 bundle install",
        "build_id": system["build_id"],
        "iso_sha256": sha256(iso),
        "bundle": bundle_meta.get("boot_bundle"),
        "checks": [],
        "status": "failed",
    }
    with tempfile.TemporaryDirectory(prefix="xos_bundle_") as folder:
        disk = Path(folder) / "fresh.img"
        create_fat32(disk, 512)
        guest = Guest(iso, "iso_bundle_install", iso=True, work_disk=disk)
        try:
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(start=start, timeout=60)
            guest.expect(b"[files] XOSBND1 bundle processed members=", start=start, timeout=60)
            guest.expect(b"members=2", start=start, timeout=10)
            report["checks"].append({"name": "bundle-processed", "passed": True})
            guest.expect(b"[files] bundle installed: /usr/bin/dash", start=start, timeout=30)
            report["checks"].append({"name": "dash-from-bundle", "passed": True})
            guest.expect(
                b"[files] bundle installed: /var/cache/xypm/incoming/idna.xpk",
                start=start, timeout=30)
            report["checks"].append({"name": "xpk-staged", "passed": True})
            pump(guest, 0.5)
            begin = len(guest.output)
            send_bytes(guest, b"ls /var/cache/xypm/incoming\r")
            guest.expect(b"idna.xpk", start=begin, timeout=20)
            report["checks"].append({"name": "incoming-listed", "passed": True})
            begin = len(guest.output)
            send_bytes(guest, b"stat /usr/bin/dash\r")
            guest.expect(b"dash", start=begin, timeout=20)
            report["checks"].append({"name": "dash-stat", "passed": True})
            begin = len(guest.output)
            send_bytes(guest, b"dash -i\r")
            guest.expect(b"$ ", start=begin, timeout=30)
            send_bytes(guest, b"echo BUNDLEDASH\r")
            guest.expect(b"BUNDLEDASH", start=begin, timeout=20)
            report["checks"].append({"name": "dash-runs", "passed": True})
            report["status"] = "passed"
        except Exception as exc:
            report["error"] = str(exc)
            report["output_tail"] = bytes(guest.output[-4000:]).decode(errors="replace")
            raise
        finally:
            guest.close()
            args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": report["checks"]}, indent=2))


if __name__ == "__main__":
    main()
