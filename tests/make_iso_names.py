# SPDX-License-Identifier: Apache-2.0
"""Inspect real ISO output and reject duplicate or unencodable file names."""
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="xos_iso_names_") as folder:
        folder = Path(folder)
        boot = folder / "boot.bin"
        boot.write_bytes(b"\x00" * 512)
        loader = folder / "loader.bin"
        loader.write_bytes(b"\x00" * 16)
        kernel = folder / "kernel.bin"
        kernel.write_bytes(b"")
        first = folder / "a"
        first.write_bytes(b"first")
        second = folder / "b"
        second.write_bytes(b"second")
        base = [sys.executable, str(ROOT / "scripts/make_iso.py"),
                "--boot", str(boot), "--loader", str(loader),
                "--kernel", str(kernel)]
        for names, label in (([("SAME.TXT", first), ("SAME.TXT", second)], "exact"),
                             ([("same.txt", first), ("SAME.TXT", second)], "case"),
                             ([("bad/name", first)], "slash")):
            output = folder / f"{label}.iso"
            command = base + ["--output", str(output)]
            for name, path in names:
                command += ["--file", f"{name}={path}"]
            run = subprocess.run(command, capture_output=True, text=True)
            if run.returncode == 0 or output.exists():
                raise AssertionError(f"{label}: duplicate/invalid name accepted")
            if "duplicate ISO file name" not in run.stderr and "invalid ISO file name" not in run.stderr:
                raise AssertionError(f"{label}: unexpected error {run.stderr!r}")
        output = folder / "layout.iso"
        subprocess.run(base + ["--output", str(output),
                               "--file", f"KERNEL.BIN={first}",
                               "--file", f"X={second}"], check=True,
                       capture_output=True, text=True)
        image = output.read_bytes()
        pvd = image[16 * 2048:17 * 2048]
        root_lba = struct.unpack_from("<I", pvd, 158)[0]
        root = image[root_lba * 2048:(root_lba + 1) * 2048]
        offset, entries = 0, {}
        while root[offset]:
            length = root[offset]
            if length % 2:
                raise AssertionError("directory record has odd length")
            entry = root[offset:offset + length]
            name_length = entry[32]
            name = entry[33:33 + name_length]
            if name_length % 2 == 0 and entry[33 + name_length] != 0:
                raise AssertionError("missing directory identifier padding")
            extent = struct.unpack_from("<I", entry, 2)[0]
            size = struct.unpack_from("<I", entry, 10)[0]
            entries[name] = image[extent * 2048:extent * 2048 + size]
            offset += length
        if entries[b"KERNEL.BIN;1"] != b"first" or entries[b"X;1"] != b"second":
            raise AssertionError("directory extents do not point to file contents")
        for field, endian in ((140, "<"), (148, ">")):
            lba = struct.unpack_from(endian + "I", pvd, field)[0]
            if lba == 0:
                raise AssertionError(f"missing {endian} endian path table")
            path = image[lba * 2048:lba * 2048 + 10]
            if (path[:2] != b"\x01\x00" or path[8:] != b"\x00\x00"
                    or struct.unpack_from(endian + "I", path, 2)[0] != root_lba
                    or struct.unpack_from(endian + "H", path, 6)[0] != 1):
                raise AssertionError(f"invalid {endian} endian root path table")
        # The record includes ';1' and optional padding; its length must be even.
        boundary = "n" * 219
        output = folder / "boundary.iso"
        run = subprocess.run(base + ["--output", str(output),
                                     "--file", f"{boundary}={first}"],
                             capture_output=True, text=True)
        if run.returncode != 0 or not output.exists():
            raise AssertionError(f"boundary: 219-char name rejected: {run.stderr!r}")
        too_long = "n" * 220
        output = folder / "too_long.iso"
        run = subprocess.run(base + ["--output", str(output),
                                     "--file", f"{too_long}={first}"],
                             capture_output=True, text=True)
        if run.returncode == 0 or output.exists():
            raise AssertionError("too-long: 220-char name accepted")
        if "Traceback" in run.stderr:
            raise AssertionError(f"too-long: traceback leaked: {run.stderr!r}")
        if "ISO file name too long" not in run.stderr:
            raise AssertionError(f"too-long: unexpected error {run.stderr!r}")
    print("ISO_NAME_CASES_OK")


if __name__ == "__main__":
    main()
