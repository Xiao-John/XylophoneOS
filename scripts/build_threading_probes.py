# SPDX-License-Identifier: Apache-2.0
"""Compile real guest probes against one frozen threading SDK."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'
SDK = BUILD / 'threading_sdk'

def main():
    tools = BUILD/'threading_probe_tools'
    tools.mkdir(exist_ok=True)
    for name in ['as', 'ld']:
        if not (tools/name).exists():
            (tools/name).symlink_to(shutil.which('x86_64-elf-'+name))
    os.environ['COMPILER_PATH'] = str(tools)
    manifest_path = SDK / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    for path, digest in manifest['artifacts'].items():
        if hashlib.sha256((SDK / path).read_bytes()).hexdigest() != digest:
            raise SystemExit('SDK artifact differs from receipt: ' + path)
    commands, artifacts = [], {}
    def run(command):
        commands.append(list(map(str, command)))
        subprocess.run(command, check=True)
    for name in ['pthread', 'cpp', 'c']:
        source = ROOT / ('tests/fixtures/threading/c_probe.c' if name == 'c' else f'tests/fixtures/threading/{name}_probe.cpp')
        obj, executable = BUILD / f'threading_{name}_probe.o', BUILD / f'threading_{name}_probe.elf'
        run(['x86_64-elf-gcc' if name == 'c' else 'x86_64-elf-g++', '-std=c11' if name == 'c' else '-std=c++20', '-O2', '-g', '-fno-pic', '-fno-pie',
             '-mno-red-zone', '-fno-stack-protector', '-ftls-model=local-exec',
             '-D_POSIX_C_SOURCE=200809L', '-DXOS_THREADED_RUNTIME',
             '-I'+str(SDK/'cpp/include'), '-I'+str(SDK/'cpp/include/x86_64-elf'),
             '-I'+str(SDK/'include'), '-c', source, '-o', obj])
        run(['x86_64-elf-g++', '-nostdlib', '-static', '-no-pie',
             '-Wl,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
             '-T', SDK/'user.ld', SDK/'crt0_posix.o', obj,
             '-Wl,--start-group', '-Wl,--whole-archive', SDK/'lib/libxos.a', '-Wl,--no-whole-archive',
             SDK/'cpp/lib/libstdc++.a', SDK/'cpp/lib/libsupc++.a', SDK/'lib/libc.a',
             SDK/'lib/libm.a', SDK/'cpp/lib/libgcc.a', '-Wl,--end-group', '-o', executable])
        artifacts[executable.name] = hashlib.sha256(executable.read_bytes()).hexdigest()
    # Deliberately use the old ELF layout, outside the threaded linker profile.
    legacy_obj, legacy = BUILD/'threading_legacy.o', BUILD/'threading_legacy.elf'
    linker = BUILD/'threading_legacy.ld'
    linker.write_text('''OUTPUT_FORMAT(elf64-x86-64)
ENTRY(_start)
PHDRS { text PT_LOAD FLAGS(5); rodata PT_LOAD FLAGS(4); legacy PT_LOAD FLAGS(6); }
SECTIONS { . = 0x40000000; .text : { *(.text) } :text
. = 0x40001000; .rodata : { *(.rodata) } :rodata
. = 0x70000000; .legacy : { *(.legacy) } :legacy
/DISCARD/ : { *(.note*) } }
''')
    run(['nasm','-f','elf64',ROOT/'tests/fixtures/threading/legacy_arena.asm','-o',legacy_obj])
    run(['x86_64-elf-ld','-T',linker,legacy_obj,'-o',legacy])
    artifacts[legacy.name] = hashlib.sha256(legacy.read_bytes()).hexdigest()
    (BUILD/'threading_probe_manifest.json').write_text(json.dumps({
        'sdk_manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        'commands':commands,'artifacts':artifacts},indent=2)+'\n')
    print('Built guest pthread/C++/legacy-layout probes')
if __name__ == '__main__': main()
