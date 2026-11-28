#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compile unchanged PCI observer implementation against fake PIO/page tables."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='xos_pci_observer_') as folder:
        temp = Path(folder)
        header = temp / 'arch/x86_64/io.hpp'
        header.parent.mkdir(parents=True)
        header.write_text('#pragma once\n#include <xos/types.hpp>\n'
                          'namespace xos::arch { void out_dword(u16,u32); '
                          'u32 in_dword(u16); void out_word(u16,u16); }\n')
        binary = temp / 'pci_observer'
        subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++20', '-O2', '-g',
                        '-Wall', '-Wextra', '-Werror', '-I', str(temp),
                        '-I', str(ROOT / 'src/kernel/include'), '-I', str(ROOT / 'src/shared/include'),
                        str(ROOT / 'src/kernel/platform/pc/pci.cpp'),
                        str(ROOT / 'tests/fixtures/ipc_device/pci_observer_host.cpp'),
                        '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    main()
