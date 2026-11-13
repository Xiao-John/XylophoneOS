# SPDX-License-Identifier: Apache-2.0
"""Apply the same newlib header fixes to upstream source and exported SDKs."""
import argparse
from pathlib import Path
import subprocess

patch_root = Path(__file__).resolve().parents[1] / "src/ports/newlib/patches"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--headers", action="store_true")
    args = parser.parse_args()
    apply_patches(args.directory, headers=args.headers)


def apply_patches(directory, *, headers=False):
    directory = Path(directory).resolve(strict=True)
    for name in ("0002_native_atomic_initialization.patch", "0003_generic_math_dispatch.patch"):
        patch = patch_root / name
        command = ["patch", "--force", "-F0", "-p4" if headers else "-p1", "-i", str(patch)]
        applied = subprocess.run([*command, "--dry-run", "--reverse"], cwd=directory,
                                 capture_output=True, text=True)
        if applied.returncode == 0:
            continue
        subprocess.run([*command, "--forward"], cwd=directory, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


if __name__ == "__main__":
    main()
