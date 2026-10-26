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
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build")
    args = parser.parse_args()
    build = args.build_dir.resolve()
    args.output = args.output or build / "xos-install-dash.iso"
    args.manifest = args.manifest or build / "install_manifest.json"
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
    configuration = system["configuration"]
    if not 0 < kernel.stat().st_size <= configuration["kernel_max_file_bytes"]:
        raise SystemExit("kernel exceeds the qualified ISO file budget")
    if not 0 < dash.stat().st_size <= configuration["iso_payload_max_bytes"]:
        raise SystemExit("dash payload exceeds the qualified ISO payload budget")
    for name, path in (("kernel.bin", kernel), ("boot_sector_iso.bin", boot), ("kernel_loader_iso_file.bin", loader)):
        expected = system["artifacts"].get(name)
        if expected is not None and sha256(path) != expected["sha256"]:
            raise SystemExit("stale system artifact: " + name)
    metadata = {
        "format": 1,
        "version": system.get("version", "0.0.1-1024"),
        "build_id": system["build_id"],
        "kernel_sha256": sha256(kernel),
        "dash_sha256": sha256(dash),
        "dash_bytes": dash.stat().st_size,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
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
