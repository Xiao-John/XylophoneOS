# SPDX-License-Identifier: Apache-2.0
"""A3/A4: boot install ISO, install dash from ISO payload, run it."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from make_work_disk import create_fat32
from task_smoke import pump, send_bytes
from work_disk import transfer


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def iso_files(path):
    image = Path(path).read_bytes()
    pvd = image[16 * 2048:17 * 2048]
    root_lba = int.from_bytes(pvd[156 + 2:156 + 6], 'little')
    root_size = int.from_bytes(pvd[156 + 10:156 + 14], 'little')
    result = {}
    block = image[root_lba * 2048:(root_lba + 1) * 2048]
    offset = 0
    while offset < root_size:
        length = block[offset]
        if length == 0:
            break
        name_len = block[offset + 32]
        name = block[offset + 33:offset + 33 + name_len].decode('ascii')
        if name not in ('.', '..', '\x00', '\x01'):
            name = name.split(';')[0]
            extent = int.from_bytes(block[offset + 2:offset + 6], 'little')
            size = int.from_bytes(block[offset + 10:offset + 14], 'little')
            result[name] = hashlib.sha256(image[extent * 2048:extent * 2048 + size]).hexdigest()
        offset += length
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "build/iso_dash_install_report.json")
    parser.add_argument("--external", action="store_true", help="start an external ELF through the newly installed dash")
    args = parser.parse_args()
    image = ROOT / "build/xos-install-dash.iso"
    metadata = json.loads((ROOT / "build/install_manifest.json").read_text())
    system = json.loads((ROOT / "build/manifest.json").read_text())
    report = {"gate": "A3/A4 ISO dash install", "build_id": system["build_id"],
              "iso_sha256": sha256(image), "manifest": metadata,
              "iso_files": iso_files(image), "checks": [], "status": "failed"}
    with tempfile.TemporaryDirectory(prefix="xos_install_") as folder:
        disk = Path(folder) / "fresh.img"
        create_fat32(disk, 512)
        if args.external:
            probe = ROOT / "build/user_hello.image.elf"
            report["external_elf_sha256"] = sha256(probe)
            if report["external_elf_sha256"] != system["artifacts"][probe.name]["sha256"]:
                raise AssertionError("external installer probe differs from the system build")
            transfer(disk, "mkdir", "/bin")
            transfer(disk, "import", "/bin/boot_probe", probe)
            script = Path(folder) / "boot_probe.sh"
            script.write_text("set -e\n/bin/boot_probe\necho A3EXTERNAL\n")
            transfer(disk, "import", "/bin/boot_probe.sh", script)
        guest = Guest(image, "iso_dash_install", iso=True, work_disk=disk)
        try:
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            bundle = metadata.get("boot_bundle")
            guest.expect_supervisor(trace=args.external, start=start, timeout=360 if bundle else 60)
            marker = b"[files] bundle installed: /usr/bin/dash" if bundle else b"[files] dash installed"
            guest.expect(marker, start=start, timeout=60)
            if args.external:
                begin = len(guest.output)
                send_bytes(guest, b"dash /bin/boot_probe.sh\r")
                guest.expect(b"hello from file", start=begin, timeout=30)
                child_output = guest.output.index(b"hello from file", begin)
                guest.expect(b"\nA3EXTERNAL\n", start=child_output, timeout=20)
                guest.expect(b"kind=exited code=0", start=child_output, timeout=20)
                guest.expect(b"xsh> ", start=child_output, timeout=20)
                report["checks"].append({"name": "dash-runs-first-external-elf", "passed": True})
            pump(guest, 0.5)
            report["checks"].append({"name": "dash-installed-from-iso", "passed": True})
            begin = len(guest.output)
            send_bytes(guest, b"type dash\r")
            guest.expect(b"dash -> /usr/bin/dash", start=begin, timeout=20)
            guest.expect(b"xsh> ", start=begin, timeout=20)
            report["checks"].append({"name": "path-visible", "passed": True})
            begin = len(guest.output)
            send_bytes(guest, b"dash -i\r")
            guest.expect(b"$ ", start=begin, timeout=30)
            send_bytes(guest, b"echo A3DASH\r")
            guest.expect(b"\nA3DASH\n", start=begin, timeout=20)
            send_bytes(guest, b"exit\r")
            guest.expect(b"xsh> ", start=begin, timeout=20)
            report["checks"].append({"name": "dash-runs", "passed": True})
            files = report["iso_files"]
            report["checks"].append({
                "name": "iso-manifest",
                "passed": (files.get("KERNEL.BIN") == metadata["kernel_sha256"] and
                           files.get("DASH.ELF") == metadata["dash_sha256"] and
                           "MANIFEST.TXT" in files),
            })
        finally:
            guest.close()
    report["status"] = "passed" if all(c["passed"] for c in report["checks"]) else "failed"
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
