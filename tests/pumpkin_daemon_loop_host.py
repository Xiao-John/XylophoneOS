#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the real Pumpkin daemon and broker with a controlled clock and mailbox."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default=os.environ.get("CXX", "c++"))
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    sources = root / "src/user/pumpkin"
    flags = ["-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror"]
    if args.sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
    with tempfile.TemporaryDirectory(prefix="pumpkin_daemon_loop_") as folder:
        fixtures = {
            "daemon_loop_host": ("daemon_protocol.cpp",),
            "broker_deadline_host": ("resource_bridge.cpp", "resource_dispatch.cpp", "sealed_blob.cpp"),
            "fat_import_host": (),
            "user_login_selector_host": (),
        }
        for name, extra in fixtures.items():
            executable = Path(folder) / name
            subprocess.run([args.cxx, *flags, "-I", root / "src/shared/include", "-I", root / "src/user/include",
                            "-I", root / "src/user", sources / "account_store.cpp", sources / "service_core.cpp",
                            *(sources / item for item in extra), root / "tests/fixtures/pumpkin" / (name + ".cpp"),
                            "-o", executable], check=True, timeout=60)
            subprocess.run([executable], check=True, timeout=30)


if __name__ == "__main__":
    main()
