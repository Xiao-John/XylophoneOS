#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build an isolated single-thread UTF-8 SDK candidate, not a qualified SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from toolchain import COMMON_FLAGS, X86_FLAGS, audit, tool
from xos_app import tree_receipt

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--newlib-prefix', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prefix = args.newlib_prefix.resolve(strict=True)
    output = args.output.resolve()
    if output.exists() or any(output.is_relative_to(p) for p in
                              (ROOT / 'src', ROOT / 'localpilot', prefix)):
        raise SystemExit('output must be a new private directory')
    receipt_path = prefix.parent / 'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    if receipt.get('profile') != 'single' or receipt.get('status') != 'built_unverified':
        raise SystemExit('expected a single multibyte candidate')
    for name, expected in receipt['artifacts'].items():
        if sha(prefix / name) != expected:
            raise SystemExit('newlib candidate differs from receipt: ' + name)
    newlib = prefix / 'x86_64-elf'
    if '#define _MB_CAPABLE 1' not in (newlib / 'include/newlib.h').read_text():
        raise SystemExit('newlib candidate lacks multibyte support')
    versions = audit()
    output.mkdir(parents=True)
    sdk = output / 'sdk'
    sdk.mkdir()
    commands = []
    def run(cmd):
        commands.append([str(x) for x in cmd])
        subprocess.run(cmd, check=True)

    sources = [ROOT / name for name in (
        'src/user/sdk/text.cpp', 'src/user/sdk/file_client.cpp', 'src/user/sdk/terminal_client.cpp',
        'src/user/arch/x86_64/syscall.cpp', 'src/shared/runtime/memory.cpp')]
    sources += sorted((ROOT / 'src/user/libc').glob('*.cpp'))
    loader_sources = [ROOT / 'src/user/loader' / name for name in
                      ('elf.cpp', 'load.cpp', 'elf_cases.cpp', 'command.cpp')]
    loader_sources.append(ROOT / 'src/user/arch/x86_64/tls.cpp')
    inputs = sources + loader_sources + [Path(__file__), ROOT / 'scripts/toolchain.py',
              ROOT / 'src/user/arch/x86_64/user.ld', ROOT / 'src/user/arch/x86_64/start.asm',
              ROOT / 'src/third_party/newlib/COPYING.NEWLIB', ROOT / 'LICENSE', ROOT / 'NOTICE']
    for directory in ('src/shared/include', 'src/user/include', 'src/third_party/fatfs', 'licenses'):
        inputs.extend(p for p in sorted((ROOT / directory).rglob('*')) if p.is_file())
    initial_inputs = {str(p.relative_to(ROOT)): sha(p) for p in inputs}
    initial_newlib_receipt = sha(receipt_path)
    try:
        shutil.copytree(newlib / 'include', sdk / 'include')
        (sdk / 'include/xos').mkdir(exist_ok=True)
        for folder in ('src/shared/include/xos', 'src/user/include/xos'):
            for header in sorted((ROOT / folder).glob('*.hpp')):
                if header.name != 'thread_core.hpp':
                    shutil.copyfile(header, sdk / 'include/xos' / header.name)
        for header in sorted((ROOT / 'src/user/include').glob('*.h')):
            shutil.copyfile(header, sdk / 'include' / header.name)
        (sdk / 'lib').mkdir()
        for name in ('libc.a', 'libm.a'):
            shutil.copyfile(newlib / 'lib' / name, sdk / 'lib' / name)
        for name in ('LICENSE', 'NOTICE'):
            shutil.copyfile(ROOT / name, sdk / name)
        shutil.copyfile(ROOT / 'src/third_party/newlib/COPYING.NEWLIB', sdk / 'COPYING.NEWLIB')
        shutil.copytree(ROOT / 'licenses', sdk / 'licenses')
        shutil.copyfile(ROOT / 'src/user/arch/x86_64/user.ld', sdk / 'user.ld')
        for name, definition in (('crt0.o', None), ('crt0_libc.o', 'XOS_LIBC'),
                                 ('crt0_posix.o', 'XOS_POSIX_MAIN')):
            cmd = ['nasm', '-f', 'elf64', '-g', '-F', 'dwarf']
            if definition:
                cmd.append('-D' + definition + '=1')
            run([*cmd, '-o', sdk / name, ROOT / 'src/user/arch/x86_64/start.asm'])
        objects = output / 'objects'
        objects.mkdir()
        for group, paths in (('xos', sources), ('loader', loader_sources)):
            members = []
            for index, source in enumerate(paths):
                obj = objects / f'{group}_{index}.o'
                flags = ['-w'] if source.parent.name == 'libc' else []
                run([tool('g++'), *COMMON_FLAGS, *X86_FLAGS, '-I', sdk / 'include',
                     '-I', ROOT / 'src/third_party/fatfs', '-I', ROOT / 'src/user/include',
                     *flags, '-c', source, '-o', obj])
                members.append(obj)
            archive = 'libxos_loader.a' if group == 'loader' else 'libxos.a'
            run([tool('ar'), 'rcsD', sdk / 'lib' / archive, *members])
        if initial_inputs != {str(p.relative_to(ROOT)): sha(p) for p in inputs}:
            raise RuntimeError('source inputs changed during build')
        if sha(receipt_path) != initial_newlib_receipt or any(
                sha(prefix / name) != expected for name, expected in receipt['artifacts'].items()):
            raise RuntimeError('newlib input changed during build')
        (sdk / 'manifest.json').write_text(json.dumps({
            'abi': 1, 'target': 'x86_64-elf', 'runtime_model': 'single',
            'profile': 'xos-utf8-experimental', 'status': 'built_unverified',
            'newlib_receipt_sha256': initial_newlib_receipt}, indent=2) + '\n')
        digest, files = tree_receipt(sdk)
        result = {'status': 'built_unverified', 'sdk_tree_sha256': digest, 'files': files}
    except Exception as error:
        result = {'status': 'failed', 'error': f'{type(error).__name__}: {error}'}
        raise
    finally:
        result.update({'newlib_receipt_sha256': initial_newlib_receipt, 'commands': commands,
                       'toolchain': versions, 'inputs': initial_inputs})
        (output / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
