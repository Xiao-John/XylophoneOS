# SPDX-License-Identifier: Apache-2.0
"""A1: read KERNEL.BIN and DASH.ELF from an ISO9660 root directory via ATAPI."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def assemble(source, output):
    subprocess.run([
        "nasm", "-f", "bin", "-Wall", "-Wno-reloc-abs-word",
        "-Wno-reloc-abs-dword", "-Werror",
        "-I", str(ROOT / "src/boot/x86") + "/",
        "-I", str(ROOT / "build") + "/",
        "-o", str(output), str(source),
    ], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "build/cd_iso9660_report.json")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="xos_iso9660_") as folder:
        folder = Path(folder)
        boot = folder / "boot.bin"
        stage = folder / "stage.bin"
        kernel = folder / "KERNEL.BIN"
        dash = folder / "DASH.ELF"
        empty = folder / "empty.bin"
        image = folder / "probe.iso"
        kernel.write_bytes(b"KERNEL!" * 300)
        dash.write_bytes(b"DASH!" * 1000)
        empty.write_bytes(b"")
        assemble(ROOT / "tests/fixtures/cd_probe/boot.asm", boot)
        assemble(ROOT / "tests/fixtures/cd_probe/iso_stage.asm", stage)
        subprocess.run([sys.executable, str(ROOT / "scripts/make_iso.py"),
                        "--boot", str(boot), "--loader", str(stage),
                        "--kernel", str(empty), "--output", str(image),
                        "--file", f"KERNEL.BIN={kernel}",
                        "--file", f"DASH.ELF={dash}"], check=True)
        image_hash = sha256(image)
        guest = Guest(image, "iso9660", iso=True)
        try:
            guest.expect(b"A1 ok KERNEL=2100 DASH=5000", timeout=20)
            passed = True
        except AssertionError:
            passed = False
        finally:
            output = bytes(guest.output)
            guest.close()
    report = {"gate": "A1 ISO9660 root read", "passed": passed,
              "iso_sha256": image_hash,
              "output_tail": output[-400:].decode("utf-8", "replace")}
    report["status"] = "passed" if passed else "failed"
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
