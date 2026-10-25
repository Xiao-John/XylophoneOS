# SPDX-License-Identifier: Apache-2.0
"""Build the install ISO with KERNEL.BIN, DASH.ELF and an ISO manifest."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from install_dash import latest_manifest, project_root


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dash-manifest", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "build/xos-install-dash.iso")
    parser.add_argument("--manifest", type=Path, default=ROOT / "build/install_manifest.json")
    args = parser.parse_args()
    build = ROOT / "build"
    boot = build / "boot_sector_iso.bin"
    loader = build / "kernel_loader_iso_file.bin"
    kernel = build / "kernel.bin"
    for path in (boot, loader, kernel):
        if not path.is_file():
            raise SystemExit(f"missing build artifact: {path}; run make build first")
    manifest = (args.dash_manifest or latest_manifest()).resolve(strict=True)
    dash_data = json.loads(manifest.read_text())
    dash = (project_root(manifest) / dash_data["elf"]).resolve(strict=True)
    if sha256(dash) != dash_data["sha256"]:
        raise SystemExit("dash ELF does not match its manifest")
    system = json.loads((build / "manifest.json").read_text())
    metadata = {
        "format": 1,
        "version": system.get("version", "0.0.1-1024"),
        "build_id": system["build_id"],
        "kernel_sha256": sha256(kernel),
        "dash_sha256": sha256(dash),
        "dash_bytes": dash.stat().st_size,
    }
    args.manifest.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    text = build / "ISO_MANIFEST.TXT"
    text.write_text("".join(f"{key}={value}\n" for key, value in metadata.items()))
    empty = build / "empty.bin"
    empty.write_bytes(b"")
    subprocess.run([
        sys.executable, str(ROOT / "scripts/make_iso.py"),
        "--boot", str(boot), "--loader", str(loader), "--kernel", str(empty),
        "--output", str(args.output),
        "--file", f"KERNEL.BIN={kernel}",
        "--file", f"DASH.ELF={dash}",
        "--file", f"MANIFEST.TXT={text}",
    ], check=True)
    print(json.dumps({**metadata, "iso": str(args.output),
                      "iso_sha256": sha256(args.output)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
