#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the native terminal and ELF support against an isolated glibc SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from glibc_g1_probe import clean_build_environment, tool_identity

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('src/ports/glibc/terminal_support.cpp', 'src/user/sdk/terminal_client.cpp',
           'src/user/arch/x86_64/syscall.cpp', 'src/ports/glibc/elf_access.cpp',
           'src/user/loader/elf.cpp')
HEADER_ROOTS = ('src/shared/include/xos', 'src/user/include/xos')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_paths():
    paths = [ROOT / name for name in SOURCES]
    paths += [p for directory in HEADER_ROOTS for p in sorted((ROOT / directory).rglob('*'))
              if p.is_file()]
    paths += list((ROOT / 'src/ports/glibc/sysdeps/xos').rglob('*.h'))
    paths += [Path(__file__).resolve(), ROOT / 'scripts/glibc_g1_probe.py',
              ROOT / 'LICENSE', ROOT / 'licenses/mit_legacy.txt']
    return sorted(set(paths))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sdk = args.sdk.resolve(strict=True)
    work = args.output.absolute()
    archive = sdk / 'usr/lib/libxos_terminal.a'
    if work.exists() or work.is_symlink() or archive.exists() or archive.is_symlink():
        parser.error('terminal output and archive must be new')
    compiler_headers = sdk / 'usr/lib/compiler-include'
    if not (sdk / 'usr/include/features.h').is_file() or not compiler_headers.is_dir():
        parser.error('install the isolated glibc and compiler headers first')
    environment, removed = clean_build_environment(os.environ)
    environment['LC_ALL'] = 'C'
    names = ('x86_64-elf-g++', 'x86_64-elf-ar', 'x86_64-elf-nm', 'x86_64-elf-objdump')
    tools = {name: tool_identity(name) for name in names}
    if any(not value['available'] for value in tools.values()):
        parser.error('target compiler, archiver and inspection tools are required')
    work.mkdir(parents=True)
    initial = {str(p.relative_to(ROOT)): sha(p) for p in input_paths()}
    report = {'status': 'building', 'profile': 'xos_glibc_terminal_v1', 'inputs': initial,
              'tools': tools, 'sanitized_environment': removed, 'steps': [],
              'guest_qualification': 'not_run'}

    def save():
        (work / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')

    def run(name, command):
        log = work / (name + '.log')
        with log.open('w') as stream:
            result = subprocess.run(command, env=environment, stdout=stream,
                                    stderr=subprocess.STDOUT)
        report['steps'].append({'name': name, 'command': command, 'exit_code': result.returncode,
                                'log_sha256': sha(log)})
        save()
        if result.returncode:
            raise RuntimeError(name + ' failed; see ' + str(log))

    try:
        # Only native xos/ interfaces enter this private include root. Generic
        # standard/libc headers must come from the glibc sysroot, never newlib.
        private_headers = work / 'include/xos'
        for directory in HEADER_ROOTS:
            source = ROOT / directory
            for path in sorted(source.rglob('*')):
                if not path.is_file():
                    continue
                target = private_headers / path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and target.read_bytes() != path.read_bytes():
                    raise RuntimeError('conflicting native header: ' + str(target))
                shutil.copyfile(path, target)
        flags = [tools['x86_64-elf-g++']['path'], '--sysroot=' + str(sdk),
                 '-std=gnu++20', '-O2', '-g', '-mno-red-zone', '-fno-pie',
                 '-fno-omit-frame-pointer', '-ffreestanding', '-fno-builtin',
                 '-fno-exceptions', '-fno-rtti', '-fno-threadsafe-statics',
                 '-fno-use-cxa-atexit', '-fno-stack-protector', '-ftls-model=local-exec',
                 '-ffunction-sections', '-fdata-sections', '-fvisibility=hidden',
                 '-nostdinc', '-nostdinc++', '-I', str(private_headers.parent),
                 '-isystem', str(sdk / 'usr/include'), '-isystem', str(compiler_headers),
                 '-Wall', '-Wextra', '-Werror']
        objects = []
        for index, relative in enumerate(SOURCES):
            target = work / (str(index) + '_' + Path(relative).stem + '.o')
            run('compile-' + str(index), flags + ['-MMD', '-MF', str(target) + '.d',
                                                 '-c', str(ROOT / relative), '-o', str(target)])
            objects.append(str(target))
        run('archive', [tools['x86_64-elf-ar']['path'], 'rcsD', str(archive), *objects])
        run('undefined', [tools['x86_64-elf-nm']['path'], '-u', str(archive)])
        run('sections', [tools['x86_64-elf-objdump']['path'], '-h', str(archive)])
        undefined = (work / 'undefined.log').read_text()
        if any(symbol in undefined for symbol in ('_impure_ptr', '_global_impure_ptr', '__getreent', '__cxa_')):
            raise RuntimeError('terminal support imported another libc or C++ runtime')
        if '.init_array' in (work / 'sections.log').read_text():
            raise RuntimeError('terminal startup must not depend on application constructors')
        if initial != {str(p.relative_to(ROOT)): sha(p) for p in input_paths()}:
            raise RuntimeError('terminal inputs changed during build')
        if any(tool_identity(name)['sha256'] != tools[name]['sha256'] for name in names):
            raise RuntimeError('terminal build tool changed during compilation')
        materials = sdk / 'usr/share/xos/terminal-support'
        for path in input_paths():
            target = materials / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        report['artifacts'] = {str(archive.relative_to(sdk)): sha(archive)}
        report['artifacts'].update({str(p.relative_to(sdk)): sha(p)
                                    for p in sorted(materials.rglob('*')) if p.is_file()})
        report['status'] = 'terminal_support_built'
        save()
    except BaseException as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        save()
        raise


if __name__ == '__main__':
    main()
