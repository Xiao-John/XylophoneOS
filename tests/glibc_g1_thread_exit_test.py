#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check native thread termination ordering and fail-closed branches."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
overlay = root / 'src/ports/glibc/sysdeps/xos'
fixture = root / 'tests/fixtures/glibc_g1/thread_exit_test.cpp'
with tempfile.TemporaryDirectory(prefix='xos_glibc_thread_exit_') as temp:
    temp = Path(temp)
    host, target, executable = temp/'host.o', temp/'target.o', temp/'test'
    subprocess.run(['clang', '-std=c11', '-Wall', '-Werror', '-DXOS_GLIBC_THREAD_TEST',
                    '-I', str(overlay), '-c', str(overlay/'xos_thread_exit.c'), '-o', str(host)], check=True)
    subprocess.run(['clang++', '-std=c++17', '-Wall', '-Werror', '-I', str(overlay),
                    '-I', str(root/'src/shared/include'), str(fixture), str(host), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
    subprocess.run(['x86_64-elf-gcc', '-std=c11', '-O2', '-ffreestanding', '-nostdinc', '-Wall', '-Werror',
                    '-I', str(overlay), '-c', str(overlay/'xos_thread_exit.c'), '-o', str(target)], check=True)
    code = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(target)], text=True)
    assert len(re.findall(r'\bint\s+\$0x80', code)) >= 3
    for number in ('2a', '2b', '2'):
        assert re.search(r'\$0x' + number + r',%eax', code)
    assert re.search(r'\bud2\b', code) and not re.search(r'\bsyscall\b', code)
print('PASS thread exit handshake, fail-closed cases and XOS target traps')
