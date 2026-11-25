#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check that the glibc static linker script retains GCC's legacy init/fini arrays."""
import re
import struct
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
linker_script = root / 'src/ports/glibc/crt/user.ld'
source = '''
extern "C" {
void first() __attribute__((constructor(200)));
void second() __attribute__((constructor(300)));
void last() __attribute__((constructor));
void first_fini() __attribute__((destructor(200)));
void second_fini() __attribute__((destructor(300)));
void last_fini() __attribute__((destructor));
void first() { asm volatile(""); }
void second() { asm volatile(""); }
void last() { asm volatile(""); }
void first_fini() { asm volatile(""); }
void second_fini() { asm volatile(""); }
void last_fini() { asm volatile(""); }
void _start() {}
}
'''


def run(*args):
    return subprocess.check_output(args, text=True)


def main():
    with tempfile.TemporaryDirectory(prefix='xos_glibc_arrays_') as temp:
        folder = Path(temp)
        cpp = folder / 'probe.cpp'
        obj = folder / 'probe.o'
        binary = folder / 'probe.elf'
        cpp.write_text(source)
        run('x86_64-elf-g++', '-O2', '-fno-pie', '-ffunction-sections', '-fno-exceptions',
            '-fno-asynchronous-unwind-tables', '-c', str(cpp), '-o', str(obj))
        sections = run('x86_64-elf-readelf', '-SW', str(obj))
        for section in ('.ctors.65335', '.ctors.65235', '.dtors.65335', '.dtors.65235'):
            assert re.search(r'\s' + re.escape(section) + r'\s', sections), section
        run('x86_64-elf-ld', '--gc-sections', '-T', str(linker_script), '-o', str(binary), str(obj))
        symbols = {name: int(address, 16) for address, name in re.findall(
            r'^([0-9a-f]+) \w (\w+)$', run('x86_64-elf-nm', '--defined-only', str(binary)), re.M)}
        for section, expected in (('init', ('first', 'second', 'last')),
                                  ('fini', ('first_fini', 'second_fini', 'last_fini'))):
            array = folder / f'{section}.bin'
            run('x86_64-elf-objcopy', '--dump-section', f'.{section}_array={array}', str(binary))
            raw = array.read_bytes() if array.is_file() else b''
            assert len(raw) == 8 * len(expected), (section, len(raw))
            assert struct.unpack('<QQQ', raw) == tuple(symbols[name] for name in expected), section
    print('PASS glibc legacy constructor and destructor arrays survive GC in priority order')


if __name__ == '__main__':
    main()
