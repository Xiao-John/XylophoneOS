# SPDX-License-Identifier: Apache-2.0
"""A0: prove the loader can read the ISO PVD through ATAPI PIO."""

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
    parser.add_argument("--report", type=Path, default=ROOT / "build/cd_atapi_report.json")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="xos_cd_probe_") as folder:
        folder = Path(folder)
        boot = folder / "boot.bin"
        stage = folder / "stage.bin"
        kernel = folder / "empty.bin"
        iso = folder / "probe.iso"
        kernel.write_bytes(b"")
        assemble(ROOT / "tests/fixtures/cd_probe/boot.asm", boot)
        assemble(ROOT / "tests/fixtures/cd_probe/stage.asm", stage)
        subprocess.run([sys.executable, str(ROOT / "scripts/make_iso.py"),
                        "--boot", str(boot), "--loader", str(stage),
                        "--kernel", str(kernel), "--output", str(iso)], check=True)
        iso_hash = sha256(iso)
        guest = Guest(iso, "cd_atapi", iso=True)
        try:
            guest.expect(b"CDTEST ok: CD001", timeout=20)
            passed = True
        except AssertionError:
            passed = False
        finally:
            output = bytes(guest.output)
            guest.close()
    report = {"gate": "A0 ATAPI PVD probe", "passed": passed,
              "iso_sha256": iso_hash,
              "output_tail": output[-400:].decode("utf-8", "replace")}
    report["status"] = "passed" if passed else "failed"
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
