# SPDX-License-Identifier: Apache-2.0
"""Launch an extracted XylophoneOS Revival disk bundle in QEMU."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
from typing import List, Optional


MACHINE = "pc-i440fx-10.0"


def qemu_executable(requested: str) -> str:
    resolved = shutil.which(requested)
    if resolved is not None:
        return resolved
    candidate = Path(requested).expanduser()
    if candidate.is_file():
        return str(candidate.resolve())
    raise FileNotFoundError(
        f"QEMU executable not found: {requested!r}. Install QEMU and retry, or pass --qemu PATH."
    )


def image_path(folder: Path, name: str) -> Path:
    path = (folder / name).expanduser().resolve()
    if "," in str(path):
        raise ValueError(
            f"Image path contains a comma, which QEMU's -drive syntax cannot represent safely: {path}. "
            "Move the extracted images to a directory whose path has no commas."
        )
    if not path.is_file():
        raise FileNotFoundError(f"Required image is missing: {path}")
    return path


def build_command(qemu: str, boot_image: Path, work_disk: Path,
                  display: Optional[str]) -> List[str]:
    command = [
        qemu,
        "-machine", MACHINE,
        "-accel", "tcg",
        "-cpu", "qemu64",
        "-m", "512",
        "-smp", "1",
        "-net", "none",
        "-boot", "order=a",
        "-drive", f"file={boot_image},format=raw,if=floppy,readonly=on",
        "-drive", f"file={work_disk},format=raw,if=ide,index=0,media=disk",
        "-serial", "stdio",
        "-monitor", "none",
    ]
    if display is None:
        command += ["-display", "none"]
    else:
        command += ["-display", display]
    return command


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image-dir", type=Path, default=Path(__file__).resolve().parent,
        help="directory containing xos.img and work_disk.img (default: this script's directory)",
    )
    parser.add_argument("--qemu", default="qemu-system-x86_64",
                        help="QEMU executable name or path")
    parser.add_argument("--display", choices=("cocoa", "gtk", "sdl"),
                        help="optional QEMU display backend; default is headless")
    args = parser.parse_args(argv)

    try:
        qemu = qemu_executable(args.qemu)
        folder = args.image_dir.expanduser().resolve()
        boot_image = image_path(folder, "xos.img")
        work_disk = image_path(folder, "work_disk.img")
        command = build_command(qemu, boot_image, work_disk, args.display)
    except (FileNotFoundError, ValueError) as error:
        print(f"launch error: {error}", file=sys.stderr)
        return 2

    print(f"Launching XylophoneOS Revival with {MACHINE}; serial console is attached to this terminal.")
    try:
        return subprocess.run(command, check=False).returncode
    except OSError as error:
        print(f"launch error: could not start QEMU: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
