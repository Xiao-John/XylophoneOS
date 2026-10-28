#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Cross-link the wide locale probe with an isolated multibyte newlib candidate.

This is a build experiment, not an SDK or target runtime qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from toolchain import COMMON_FLAGS, X86_FLAGS, audit, tool
from xos_app import tree_receipt

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--newlib-prefix', required=True, type=Path)
    parser.add_argument('--sdk', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    prefix = args.newlib_prefix.resolve(strict=True)
    sdk = args.sdk.resolve(strict=True)
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(ROOT / 'src') or output.is_relative_to(ROOT / 'localpilot') or output.is_relative_to(sdk) or output.is_relative_to(prefix):
        raise SystemExit('output must be a new private directory')
    receipt = json.loads((prefix.parent / 'receipt.json').read_text())
    if receipt.get('profile') != 'single' or receipt.get('status') != 'built_unverified':
        raise SystemExit('expected isolated single newlib candidate receipt')
    for name, expected in receipt['artifacts'].items():
        if sha(prefix / name) != expected:
            raise SystemExit('candidate differs from receipt: ' + name)
    newlib = prefix / 'x86_64-elf'
    if '#define _MB_CAPABLE 1' not in (newlib / 'include/newlib.h').read_text():
        raise SystemExit('candidate lacks multibyte support')
    versions = audit()
    sdk_hash, _ = tree_receipt(sdk)
    output.mkdir(parents=True)
    commands = []
    def run(command):
        commands.append(command)
        subprocess.run(command, check=True)

    sources = [ROOT / name for name in (
        'src/user/sdk/text.cpp', 'src/user/sdk/file_client.cpp',
        'src/user/arch/x86_64/syscall.cpp', 'src/shared/runtime/memory.cpp')]
    sources += sorted((ROOT / 'src/user/libc').glob('*.cpp'))
    objects = []
    try:
        for index, source in enumerate(sources):
            obj = output / f'object_{index}.o'
            cmd = [tool('g++'), *COMMON_FLAGS, *X86_FLAGS, '-I', str(ROOT / 'src/user/include'),
                   '-I', str(newlib / 'include'),
                   '-I', str(sdk / 'include'), '-I', str(ROOT / 'src/third_party/fatfs'),
                   '-I', str(ROOT / 'src/user/include')]
            if source.parent.name == 'libc':
                cmd.append('-w')
            run([*cmd, '-c', str(source), '-o', str(obj)])
            objects.append(str(obj))
        archive = output / 'libxos_probe.a'
        run([tool('ar'), 'rcsD', str(archive), *objects])
        elf = output / 'wide_locale_probe.elf'
        run([tool('gcc'), '-O2', '-mno-red-zone', '-fno-pie', '-fno-pic',
             '-fno-stack-protector', '-ftls-model=local-exec', '-std=c11',
             '-I', str(ROOT / 'src/user/include'), '-I', str(newlib / 'include'),
             '-idirafter', str(sdk / 'include'),
             '-nostdlib', '-static', '-no-pie',
             '-Wl,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
             '-T', str(sdk / 'user.ld'), str(sdk / 'crt0_posix.o'),
             str(ROOT / 'tests/fixtures/ncursesw/wide_locale_probe.c'), '-Wl,--start-group',
             str(archive), str(sdk / 'lib/libxos_loader.a'), str(newlib / 'lib/libc.a'),
             str(newlib / 'lib/libm.a'), '-lgcc', '-Wl,--end-group', '-o', str(elf)])
        if tree_receipt(sdk)[0] != sdk_hash:
            raise RuntimeError('SDK changed during probe')
        result = {'status': 'cross_linked_guest_not_run', 'elf_sha256': sha(elf)}
    except Exception as error:
        result = {'status': 'failed', 'error': f'{type(error).__name__}: {error}'}
        raise
    finally:
        result.update({'commands': commands, 'toolchain': versions,
                       'newlib_receipt_sha256': sha(prefix.parent / 'receipt.json'),
                       'sdk_tree_sha256': sdk_hash,
                       'inputs': {str(p.relative_to(ROOT)): sha(p) for p in sources + [
                           ROOT / 'tests/fixtures/ncursesw/wide_locale_probe.c', Path(__file__)] +
                           sorted(p for p in (ROOT / 'src/user/include').rglob('*') if p.is_file())}})
        (output / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
