#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise XOS wait ABI marshalling and inspect the real target trap."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
overlay = root / 'src/ports/glibc/sysdeps/xos'
fixture = root / 'tests/fixtures/glibc_g1/wait_word_test.cpp'
with tempfile.TemporaryDirectory(prefix='xos_glibc_wait_') as temp:
    temp = Path(temp)
    host_obj, target_obj, executable = temp/'host.o', temp/'target.o', temp/'test'
    subprocess.run(['clang', '-std=c11', '-Wall', '-Werror', '-DXOS_GLIBC_WAIT_TEST',
                    '-I', str(overlay), '-c', str(overlay/'xos_wait_word.c'), '-o', str(host_obj)], check=True)
    subprocess.run(['clang++', '-std=c++17', '-Wall', '-Werror', '-I', str(overlay),
                    '-I', str(root/'src/shared/include'), str(fixture), str(host_obj),
                    '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
    subprocess.run(['x86_64-elf-gcc', '-std=c11', '-O2', '-ffreestanding', '-nostdinc',
                    '-Wall', '-Werror', '-I', str(overlay), '-c', str(overlay/'xos_wait_word.c'),
                    '-o', str(target_obj)], check=True)
    code = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(target_obj)], text=True)
    assert len(re.findall(r'\bint\s+\$0x80', code)) == 2
    assert re.search(r'\$0x30,%eax', code) and re.search(r'\$0x31,%eax', code)
    assert not re.search(r'\bsyscall\b|R_X86_64_', code)
print('PASS wait ABI marshalling, XOS contract layout, raw results and target traps')
