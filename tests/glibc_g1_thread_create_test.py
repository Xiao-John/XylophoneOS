#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check native thread request layout and target traps, not pthread behavior."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
overlay = root / 'src/ports/glibc/sysdeps/xos'
with tempfile.TemporaryDirectory(prefix='xos_glibc_thread_') as tmp:
    tmp = Path(tmp)
    host, target, exe = tmp/'host.o', tmp/'target.o', tmp/'test'
    subprocess.run(['clang', '-std=c11', '-Wall', '-Werror', '-DXOS_GLIBC_THREAD_TEST',
                    '-I', str(overlay), '-c', str(overlay/'xos_thread_create.c'), '-o', str(host)], check=True)
    subprocess.run(['clang++', '-std=c++17', '-Wall', '-Werror', '-I', str(overlay),
                    '-I', str(root/'src/shared/include'), str(root/'tests/fixtures/glibc_g1/thread_create_test.cpp'),
                    str(host), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
    subprocess.run(['x86_64-elf-gcc', '-std=c11', '-O2', '-ffreestanding', '-nostdinc', '-Wall', '-Werror',
                    '-I', str(overlay), '-c', str(overlay/'xos_thread_create.c'), '-o', str(target)], check=True)
    code = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(target)], text=True)
    assert len(re.findall(r'\bint\s+\$0x80', code)) == 3
    for number in ('26', '27', '28'):
        assert re.search(r'\$0x' + number + r',%eax', code)
    assert not re.search(r'\bsyscall\b|R_X86_64_', code)
print('PASS native thread request layouts, raw outcomes and XOS target traps')
