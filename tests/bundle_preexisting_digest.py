# SPDX-License-Identifier: Apache-2.0
"""A same-size but different /usr/bin/dash must not be reported as installed."""
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
from work_disk import transfer


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    idna = ROOT / "build/idna-3.20.xpk"
    if not idna.is_file():
        raise SystemExit("missing idna xpk")
    iso = ROOT / "build/iso_bundle_preexisting.iso"
    manifest = ROOT / "build/iso_bundle_preexisting_manifest.json"
    subprocess.run([
        sys.executable, str(ROOT / "scripts/build_install_iso.py"),
        "--output", str(iso), "--manifest", str(manifest),
        "--member", f"4:idna.xpk={idna}",
    ], check=True, cwd=ROOT)
    bundle = json.loads(manifest.read_text())["boot_bundle"]
    dash = next(m for m in bundle["members"] if m["type"] == 1)
    length = dash["data_len"]
    system = json.loads((ROOT / "build/manifest.json").read_text())
    report = {"gate": "XOSBND1 preexisting same-size target", "build_id": system["build_id"],
              "iso_sha256": sha256(iso), "dash_len": length, "checks": [], "status": "failed"}
    with tempfile.TemporaryDirectory(prefix="xos_bundle_preexisting_") as folder:
        folder = Path(folder)
        dummy = folder / "dummy.elf"
        dummy.write_bytes(b"X" * length)
        disk = folder / "work.img"
        create_fat32(disk, 512)
        for name in ("/usr", "/usr/bin"):
            transfer(disk, "mkdir", name)
        transfer(disk, "import", "/usr/bin/dash", dummy)
        guest = Guest(iso, "bundle_preexisting", iso=True, work_disk=disk)
        try:
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(start=start, timeout=60)
            guest.expect(b"[files] bundle conflict: /usr/bin/dash digest",
                         start=start, timeout=60)
            report["checks"].append({"name": "same-size-different-digest-rejected",
                                     "passed": True})
            begin = len(guest.output)
            send_bytes(guest, b"dash -i\r")
            guest.expect_any((b"not found", b"not executable"), start=begin, timeout=20)
            pump(guest, 0.3)
            if b"$ " in bytes(guest.output[begin:]):
                raise AssertionError("planted payload ran as dash")
            report["checks"].append({"name": "planted-dash-not-runnable", "passed": True})
            report["status"] = "passed"
        except Exception as exc:
            report["error"] = str(exc)
            raise
        finally:
            guest.close()
    (ROOT / "build/iso_bundle_preexisting_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: preexisting same-size digest gate")


if __name__ == "__main__":
    main()
