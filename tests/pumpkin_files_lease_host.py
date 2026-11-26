#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify the opt-in files slot lease and staging core on the host."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    flags = ["-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror"]
    if args.sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
    with tempfile.TemporaryDirectory(prefix="pumpkin_lease_") as directory:
        program = Path(directory) / "files_private_lease"
        subprocess.run([os.environ.get("CXX", "c++"), *flags, "-I", root / "src/shared/include",
                        "-I", root / "src/user/include", "-I", root / "src/user",
                        root / "src/user/services/files_private_lease.cpp",
                        root / "src/user/services/files_private_broker.cpp",
                        root / "tests/fixtures/pumpkin/files_private_lease_host.cpp",
                        "-o", program], check=True, timeout=60)
        subprocess.run([program], check=True, timeout=30)


if __name__ == "__main__":
    main()
