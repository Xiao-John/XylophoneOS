# SPDX-License-Identifier: Apache-2.0
"""make_iso rejects duplicate or invalid root file names."""
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
        # name + ';1' must fit the single-byte record length fields: 220 ok, 221 not
        boundary = "n" * 220
        output = folder / "boundary.iso"
        run = subprocess.run(base + ["--output", str(output),
                                     "--file", f"{boundary}={first}"],
                             capture_output=True, text=True)
        if run.returncode != 0 or not output.exists():
            raise AssertionError(f"boundary: 220-char name rejected: {run.stderr!r}")
        too_long = "n" * 221
        output = folder / "too_long.iso"
        run = subprocess.run(base + ["--output", str(output),
                                     "--file", f"{too_long}={first}"],
                             capture_output=True, text=True)
        if run.returncode == 0 or output.exists():
            raise AssertionError("too-long: 221-char name accepted")
        if "Traceback" in run.stderr:
            raise AssertionError(f"too-long: traceback leaked: {run.stderr!r}")
        if "ISO file name too long" not in run.stderr:
            raise AssertionError(f"too-long: unexpected error {run.stderr!r}")
    print("ISO_NAME_CASES_OK")


if __name__ == "__main__":
    main()
