# SPDX-License-Identifier: Apache-2.0
"""Exercise production device store and allocator using Linux shared maps.

The fixture replaces privileged page-table and PCI/PIC operations, not the
grant lifecycle or physical-page allocator. This is not guest qualification.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="xos_ipc_device_") as temporary:
        binary = Path(temporary) / "grants_host"
        subprocess.run([os.environ.get("CXX", "c++"), "-std=c++20", "-O2", "-Wall",
                        "-Wextra", "-Werror", "-I", str(ROOT / "src/kernel"),
                        "-I", str(ROOT / "src/kernel/include"), "-I", str(ROOT / "src/shared/include"),
                        str(ROOT / "tests/fixtures/ipc_device/grants_host.cpp"),
                        str(ROOT / "src/kernel/core/memory.cpp"), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], cwd=temporary, check=True)


if __name__ == "__main__":
    main()
