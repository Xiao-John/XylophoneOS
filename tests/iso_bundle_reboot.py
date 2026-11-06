# SPDX-License-Identifier: Apache-2.0
"""DU4 reboot idempotency: boot a bundle ISO, write /out/marker, shut down,
boot again — already-present path, marker survives, dash still runs."""
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path,
                        default=ROOT / "build/iso_bundle_reboot_report.json")
    parser.add_argument("--idna", type=Path, default=ROOT / "build/idna-3.20.xpk")
    args = parser.parse_args()
    if not args.idna.is_file():
        raise SystemExit(f"missing idna xpk: {args.idna}")

    iso = ROOT / "build/iso_bundle_reboot.iso"
    manifest = ROOT / "build/iso_bundle_reboot_manifest.json"
    subprocess.run([
        sys.executable, str(ROOT / "scripts/build_install_iso.py"),
        "--output", str(iso),
        "--manifest", str(manifest),
        "--member", f"4:idna.xpk={args.idna}",
    ], check=True, cwd=ROOT)
    bundle_meta = json.loads(manifest.read_text())
    members = bundle_meta.get("boot_bundle", {}).get("members", [])
    if len(members) < 2:
        raise SystemExit(f"expected dash+idna bundle, got {members}")

    system = json.loads((ROOT / "build/manifest.json").read_text())
    report = {
        "gate": "DU4 XOSBND1 bundle reboot idempotency",
        "build_id": system["build_id"],
        "iso_sha256": hashlib.sha256(iso.read_bytes()).hexdigest(),
        "bundle": bundle_meta.get("boot_bundle"),
        "checks": [],
        "status": "failed",
    }

    def command(guest, data, expected, start=None, timeout=30):
        begin = len(guest.output) if start is None else start
        send_bytes(guest, data)
        guest.expect(expected, start=begin, timeout=timeout)
        pump(guest, 0.2)
        return bytes(guest.output[begin:])

    with tempfile.TemporaryDirectory(prefix="xos_bundle_reboot_") as folder:
        disk = Path(folder) / "reboot.img"
        create_fat32(disk, 512)

        def boot(name):
            guest = Guest(iso, name, iso=True, work_disk=disk)
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(start=start, timeout=60)
            return guest, start

        guest, start = boot("iso_bundle_reboot")
        try:
            guest.expect_supervisor(start=start, timeout=60)
            if b"members=2" not in bytes(guest.output):
                raise AssertionError("missing members=2 in output")
            guest.expect(b"[files] bundle installed: /usr/bin/dash",
                         start=start, timeout=10)
            report["checks"].append({"name": "first-boot-installed",
                                     "passed": True})
            command(guest, b"mkdir /out\r",
                    b"[files] directory created /out")
            command(guest, b"edit /out/marker\r", b"| ")
            command(guest, b"REBOOTMARK\r", b"| ")
            command(guest, b":wq\r", b"xsh> ")
            sync_out = command(guest, b"sync\r", b"[files] sync=ok")
            if b"[files] sync=ok" not in sync_out:
                raise AssertionError(f"sync failed: {sync_out!r}")
            report["checks"].append({"name": "marker-written-synced",
                                     "passed": True})
            cat_out = command(guest, b"cat /out/marker\r", b"xsh> ")
            if b"REBOOTMARK" not in cat_out:
                raise AssertionError(f"marker unread: {cat_out!r}")
            begin = len(guest.output)
            send_bytes(guest, b"dash -i\r")
            guest.expect(b"$ ", start=begin, timeout=30)
            send_bytes(guest, b"echo FIRSTBOOT\r")
            guest.expect(b"FIRSTBOOT", start=begin, timeout=20)
            send_bytes(guest, b"exit\r")
            guest.expect_any((b"xsh> ", b"sup> "), start=begin, timeout=20)
            report["checks"].append({"name": "first-boot-dash-runs",
                                     "passed": True})
        except Exception as exc:
            report["error"] = "first boot: " + str(exc)
            report["output_tail"] = bytes(guest.output[-4000:]).decode(
                errors="replace")
            raise
        finally:
            guest.close()

        guest, start = boot("iso_bundle_reboot_2")
        try:
            guest.expect(b"[files] bundle already present: /usr/bin/dash",
                         start=start, timeout=30)
            report["checks"].append({"name": "second-boot-already-present",
                                     "passed": True})
            if b"members=2" not in bytes(guest.output[start:]):
                raise AssertionError("second boot missing members=2")
            report["checks"].append({"name": "second-boot-idempotent",
                                     "passed": True})
            window = bytes(guest.output[start:])
            xpk_new = b"bundle installed: /var/cache/xypm/incoming/idna.xpk"
            xpk_old = b"bundle already present: /var/cache/xypm/incoming/idna.xpk"
            if xpk_new not in window and xpk_old not in window:
                raise AssertionError("xpk member neither installed nor present")
            report["checks"].append({
                "name": "xpk-member-idempotent",
                "passed": True,
                "already_present": xpk_old in window,
            })
            cat_out = command(guest, b"cat /out/marker\r", b"xsh> ")
            if b"REBOOTMARK" not in cat_out:
                raise AssertionError(f"marker lost after reboot: {cat_out!r}")
            report["checks"].append({"name": "marker-survives-reboot",
                                     "passed": True})
            begin = len(guest.output)
            send_bytes(guest, b"dash -i\r")
            guest.expect(b"$ ", start=begin, timeout=30)
            send_bytes(guest, b"echo SECONDBOOT\r")
            guest.expect(b"SECONDBOOT", start=begin, timeout=20)
            send_bytes(guest, b"exit\r")
            guest.expect_any((b"xsh> ", b"sup> "), start=begin, timeout=20)
            report["checks"].append({"name": "second-boot-dash-runs",
                                     "passed": True})
            report["status"] = "passed"
        except Exception as exc:
            report["error"] = report.get("error", "") + " second boot: " + str(exc)
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
