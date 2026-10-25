# SPDX-License-Identifier: Apache-2.0
"""Install a built dash ELF into an XOS work disk as /usr/bin/dash."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from work_disk import transfer

DEFAULT_PATH = "/usr/bin/dash"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def project_root(manifest):
    for parent in Path(manifest).resolve().parents:
        if (parent / "src/ports/dash").is_dir():
            return parent
    raise SystemExit(f"cannot locate project root from {manifest}")


def latest_manifest(root=ROOT):
    manifests = sorted(
        (root / ".cache/xos_seed/dash").glob("*/manifest.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for manifest in manifests:
        data = json.loads(manifest.read_text())
        if data.get("status") == "built_not_run":
            return manifest
    raise SystemExit("no built dash manifest; run scripts/build_dash.py first")


def install(disk, manifest=None, path=DEFAULT_PATH):
    disk = Path(disk)
    if not disk.is_file():
        raise SystemExit(f"work disk not found: {disk}; run make disk first")
    manifest = Path(manifest).resolve(strict=True) if manifest else latest_manifest()
    data = json.loads(manifest.read_text())
    root = project_root(manifest)
    elf = (root / data["elf"]).resolve(strict=True)
    if sha256(elf) != data["sha256"]:
        raise SystemExit("dash ELF does not match its manifest")
    chain = ""
    for part in Path(path).parent.as_posix().strip("/").split("/"):
        chain += "/" + part
        try:
            transfer(disk, "mkdir", chain)
        except subprocess.CalledProcessError:
            pass
    transfer(disk, "import", path, elf)
    return {"installed": path, "disk": str(disk), "elf": str(elf),
            "sha256": data["sha256"], "bytes": data["bytes"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--disk", type=Path, default=ROOT / "work_disk.img")
    parser.add_argument("--path", default=DEFAULT_PATH)
    args = parser.parse_args()
    print(json.dumps(install(args.disk, args.manifest, args.path), indent=2))


if __name__ == "__main__":
    main()
