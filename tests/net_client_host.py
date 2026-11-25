#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the production native-network SDK with a controlled IPC boundary."""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="xos_net_client_") as temporary:
    binary = Path(temporary) / "client"
    subprocess.run([os.environ.get("CXX", "c++"), "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I", str(root / "src/shared/include"), "-idirafter", str(root / "src/user/include"),
                    str(root / "tests/fixtures/network/client_host.cpp"), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
