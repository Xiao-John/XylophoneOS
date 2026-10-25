#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compile one C/C++ source with the exact sibling XOS threading SDK."""
import argparse
from pathlib import Path
import subprocess
import os
import shutil
import tempfile
import hashlib
import json
SDK = Path(__file__).resolve().parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('source', type=Path)
p.add_argument('-o', '--output', required=True, type=Path)
p.add_argument('--c', action='store_true')
a = p.parse_args()
target_tools = tempfile.TemporaryDirectory(prefix='xos_target_tools_')
for name in ['as', 'ld']:
    selected = shutil.which('x86_64-elf-' + name)
    if not selected:
        raise SystemExit('Missing x86_64-elf-' + name)
    (Path(target_tools.name)/name).symlink_to(selected)
os.environ['COMPILER_PATH'] = target_tools.name
manifest = json.loads((SDK/'manifest.json').read_text())
for relative, digest in manifest['artifacts'].items():
    path = SDK/relative
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise SystemExit('Threading SDK artifact differs from its receipt: ' + relative)
obj = a.output.with_suffix('.xos.o')
flags = ['-O2','-g','-fno-pic','-fno-pie','-mno-red-zone','-fno-stack-protector',
         '-ftls-model=local-exec','-DXOS_THREADED_RUNTIME','-D_POSIX_C_SOURCE=200809L','-I'+str(SDK/'include')]
if not a.c:
    flags += ['-I'+str(SDK/'cpp/include'),'-I'+str(SDK/'cpp/include/x86_64-elf')]
subprocess.run(['x86_64-elf-gcc' if a.c else 'x86_64-elf-g++',
                '-std=c11' if a.c else '-std=c++20',*flags,'-c',str(a.source),'-o',str(obj)],check=True)
subprocess.run(['x86_64-elf-g++','-nostdlib','-static','-no-pie',
 '-Wl,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
 '-T',str(SDK/'user.ld'),str(SDK/'crt0_posix.o'),str(obj),
 '-Wl,--start-group','-Wl,--whole-archive',str(SDK/'lib/libxos.a'),'-Wl,--no-whole-archive',
 *[str(SDK/x) for x in ['cpp/lib/libstdc++.a','cpp/lib/libsupc++.a','lib/libc.a','lib/libm.a','cpp/lib/libgcc.a']],
 '-Wl,--end-group','-o',str(a.output)],check=True)
