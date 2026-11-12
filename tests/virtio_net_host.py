# SPDX-License-Identifier: Apache-2.0
"""Test the production PCI capability parser and split-ring driver on the host.

Only the actual device completion records are supplied by the fixture. Syscall
transport/PCI/IRQ delivery are not executed and no guest pass is implied.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="xos_virtio_net_") as temporary:
        binary = Path(temporary) / "virtio_net_host"
        subprocess.run([os.environ.get("CXX", "c++"), "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
                        "-I", str(ROOT / "src/user"), "-I", str(ROOT / "src/shared/include"),
                        "-idirafter", str(ROOT / "src/user/include"),
                        str(ROOT / "tests/fixtures/ipc_device/virtio_net_host.cpp"),
                        str(ROOT / "src/user/drivers/virtio_net.cpp"), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], cwd=temporary, check=True)


if __name__ == "__main__":
    main()
