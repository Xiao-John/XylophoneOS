#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the disposable durable-daemon slot selector on the host."""

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
    with tempfile.TemporaryDirectory(prefix="pumpkin_disk_store_") as directory:
        program = Path(directory) / "disk_store"
        subprocess.run([os.environ.get("CXX", "c++"), *flags, "-I", root / "src/shared/include",
                        "-I", root / "src/user/include", "-I", root / "src/user",
                        root / "src/user/pumpkin/account_store.cpp", root / "src/user/pumpkin/disk_test_store.cpp",
                        root / "tests/fixtures/pumpkin/disk_test_store_host.cpp", "-o", program],
                       check=True, timeout=60)
        subprocess.run([program], check=True, timeout=30)


if __name__ == "__main__":
    main()
