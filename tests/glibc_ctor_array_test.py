#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check static CRT fragment retention and GCC constructor ordering with and without GC."""
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
void unrelated() { asm volatile(""); }
void _init();
void _fini();
__attribute__((section(".text.entry"))) void _start() { _init(); _fini(); }
}
'''
crt_fragments = {
    'crti': '''
.section .init,"ax"
.globl _init
_init: push %rax
.section .fini,"ax"
.globl _fini
_fini: push %rdx
''',
    'crt_body': '''
.section .init,"ax"
    nop
.section .fini,"ax"
    nop
    nop
''',
    'crtn': '''
.section .init,"ax"
    pop %rax
    ret
.section .fini,"ax"
    pop %rdx
    ret
''',
}


def run(*args):
    return subprocess.check_output(args, text=True)


def dump_section(binary, section):
    output = binary.with_suffix(section + '.bin')
    copy = binary.with_suffix('.copy.elf')
    run('x86_64-elf-objcopy', '--dump-section', f'{section}={output}', str(binary), str(copy))
    return output.read_bytes()


def check_binary(binary, gc):
    symbols = {name: int(address, 16) for address, name in re.findall(
        r'^([0-9a-f]+) \w (\w+)$', run('x86_64-elf-nm', '--defined-only', str(binary)), re.M)}
    text = dump_section(binary, '.text')
    for name, expected in (('_init', b'\x50\x90\x58\xc3'), ('_fini', b'\x52\x90\x90\x5a\xc3')):
        offset = symbols[name] - symbols['_start']
        assert text[offset:offset + len(expected)] == expected, (name, 'GC' if gc else 'ordinary')
    assert ('unrelated' in symbols) == (not gc), 'unused function survived garbage collection'
    for section, expected in (('.init_array', ('first', 'second', 'last')),
                              ('.fini_array', ('first_fini', 'second_fini', 'last_fini'))):
        raw = dump_section(binary, section)
        assert len(raw) == 8 * len(expected), (section, len(raw))
        assert struct.unpack('<QQQ', raw) == tuple(symbols[name] for name in expected), section


def main():
    with tempfile.TemporaryDirectory(prefix='xos_glibc_arrays_') as temp:
        folder = Path(temp)
        cpp = folder / 'probe.cpp'
        obj = folder / 'probe.o'
        cpp.write_text(source)
        run('x86_64-elf-g++', '-O2', '-fno-pie', '-ffunction-sections', '-fno-exceptions',
            '-fno-asynchronous-unwind-tables', '-c', str(cpp), '-o', str(obj))
        sections = run('x86_64-elf-readelf', '-SW', str(obj))
        for section in ('.ctors.65335', '.ctors.65235', '.dtors.65335', '.dtors.65235'):
            assert re.search(r'\s' + re.escape(section) + r'\s', sections), section
        for name, assembly in crt_fragments.items():
            path = folder / (name + '.s')
            path.write_text(assembly)
            run('x86_64-elf-as', '-o', str(path.with_suffix('.o')), str(path))
        objects = [folder / 'crti.o', folder / 'crt_body.o', obj, folder / 'crtn.o']
        for gc in (False, True):
            binary = folder / ('gc.elf' if gc else 'ordinary.elf')
            options = ('--gc-sections',) if gc else ()
            run('x86_64-elf-ld', *options, '-T', str(linker_script), '-o', str(binary), *map(str, objects))
            check_binary(binary, gc)
    print('PASS ordinary and GC links retain complete glibc CRT hooks and ordered legacy arrays')


if __name__ == '__main__':
    main()
