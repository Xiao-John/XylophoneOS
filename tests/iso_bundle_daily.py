# SPDX-License-Identifier: Apache-2.0
"""DU4: boot an XOSBND1 ISO with daily (type3) and idna (type4) members on an empty disk."""
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

MAX_CONTAINER_BYTES = 33554432


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "build/iso_bundle_daily_report.json")
    parser.add_argument("--daily", type=Path, default=ROOT / "build/daily_utils_002.xpk")
    parser.add_argument("--idna", type=Path, default=ROOT / "build/idna-3.20.xpk")
    args = parser.parse_args()
    for path in (args.daily, args.idna):
        if not path.is_file():
            raise SystemExit(f"missing member xpk: {path}")

    iso = ROOT / "build/iso_bundle_daily.iso"
    manifest = ROOT / "build/iso_bundle_daily_manifest.json"
    system = json.loads((ROOT / "build/manifest.json").read_text())
    report = {
        "gate": "DU4 XOSBND1 daily+aux bundle on empty disk",
        "build_id": system["build_id"],
        "member_specs": [
            f"3:daily={args.daily}",
            f"4:idna={args.idna}",
        ],
        "checks": [],
        "status": "failed",
    }
    guest = None
    try:
        subprocess.run([
            sys.executable, str(ROOT / "scripts/build_install_iso.py"),
            "--output", str(iso),
            "--manifest", str(manifest),
            "--member", f"3:daily={args.daily}",
            "--member", f"4:idna={args.idna}",
        ], check=True, cwd=ROOT)
        bundle_meta = json.loads(manifest.read_text())
        bundle = bundle_meta.get("boot_bundle")
        if bundle is None:
            raise SystemExit("install manifest has no boot_bundle metadata")
        report["bundle"] = bundle
        report["iso_sha256"] = sha256(iso)

        container_bytes = bundle.get("container_bytes", 0)
        if not 0 < container_bytes <= MAX_CONTAINER_BYTES:
            raise SystemExit(f"container total {container_bytes} exceeds {MAX_CONTAINER_BYTES}")
        report["checks"].append({"name": "container-budget", "passed": True,
                                 "container_bytes": container_bytes,
                                 "limit": MAX_CONTAINER_BYTES})

        members = bundle.get("members", [])
        if len(members) != 3:
            raise SystemExit(f"expected 3 bundle members, got {members}")
        kinds = {(m.get("type"), m.get("name")) for m in members}
        if (1, "dash") not in kinds:
            raise SystemExit(f"dash member missing from metadata: {members}")
        if (3, "daily") not in kinds or (4, "idna") not in kinds:
            raise SystemExit(f"daily/idna members missing from metadata: {members}")
        report["checks"].append({"name": "bundle-metadata-3-members", "passed": True,
                                 "members": members})

        with tempfile.TemporaryDirectory(prefix="xos_bundle_daily_") as folder:
            disk = Path(folder) / "fresh.img"
            create_fat32(disk, 512)
            guest = Guest(iso, "iso_bundle_daily", iso=True, work_disk=disk)
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            # The shell prompt waits on files-service init, and init stages the
            # 11.4 MiB daily member first; watch the install messages directly.
            guest.expect(b"[files] bundle installed: /usr/bin/dash", start=start, timeout=180)
            report["checks"].append({"name": "dash-from-bundle", "passed": True})
            guest.expect(
                b"[files] bundle installed: /var/cache/xypm/incoming/daily",
                start=start, timeout=900)
            report["checks"].append({"name": "daily-staged", "passed": True})
            guest.expect(
                b"[files] bundle installed: /var/cache/xypm/incoming/idna",
                start=start, timeout=300)
            report["checks"].append({"name": "idna-staged", "passed": True})
            guest.expect(b"[files] XOSBND1 bundle processed members=", start=start, timeout=300)
            guest.expect(b"members=3", start=start, timeout=10)
            report["checks"].append({"name": "bundle-processed-members-3", "passed": True})
            guest.expect_supervisor(start=start, timeout=300)
            pump(guest, 0.5)
            begin = len(guest.output)
            send_bytes(guest, b"ls /var/cache/xypm/incoming\r")
            guest.expect(b"daily", start=begin, timeout=60)
            guest.expect(b"idna", start=begin, timeout=20)
            report["checks"].append({"name": "incoming-listed", "passed": True})
            report["status"] = "passed"
    except Exception as exc:
        report["error"] = str(exc)
        if guest is not None:
            report["output_tail"] = bytes(guest.output[-4000:]).decode(errors="replace")
        raise
    finally:
        if guest is not None:
            guest.close()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": report["checks"]}, indent=2))


if __name__ == "__main__":
    main()
