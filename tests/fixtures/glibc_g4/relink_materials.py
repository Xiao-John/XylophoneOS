# SPDX-License-Identifier: Apache-2.0
"""Link a retained static probe from the staged replacement materials."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', choices=('original', 'replacement'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / 'link.json').read_text())
    destination = args.output.absolute()
    if destination.exists() or destination.is_symlink():
        parser.error('choose a new output file')
    for name, expected in manifest['inputs'].items():
        if digest(root / name) != expected:
            parser.error('input differs from the manifest: ' + name)
    tools = {}
    for name, expected in manifest['tools'].items():
        executable = shutil.which('x86_64-elf-' + name)
        if not executable or digest(Path(executable)) != expected:
            parser.error('tool differs from the manifest: ' + name)
        tools[name] = Path(executable).resolve()

    sysroot = root / 'sysroot'
    lib = sysroot / 'usr/lib'
    libc = root / 'replacement/libc.a' if args.runtime == 'replacement' else lib / 'libc.a'
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='link_') as folder:
        tool_paths = Path(folder)
        for name in ('as', 'ld'):
            (tool_paths / name).symlink_to(tools[name])
        output = tool_paths / 'application.elf'
        command = [str(tools['gcc']), '--sysroot=' + str(sysroot), '-B' + folder + '/',
                   '-static', '-no-pie', '-nostdlib', '-Wl,--build-id=none',
                   '-Wl,-z,noexecstack', '-Wl,-z,max-page-size=4096', '-T', str(sysroot / 'user.ld'),
                   '-o', str(output), *map(str, (lib / name for name in
                       ('xos_start.o', 'crti.o', 'crtbegin.o', 'xos_start_c.o'))),
                   str(root / 'program_0.o'), '-Wl,--start-group', str(libc),
                   *map(str, (lib / name for name in ('libm.a', 'libxos_terminal.a', 'libgcc.a'))),
                   '-Wl,--end-group', str(lib / 'crtend.o'), str(lib / 'crtn.o')]
        subprocess.run(command, check=True)
        result = digest(output)
        if result != manifest['outputs'][args.runtime]:
            raise SystemExit('linked ELF differs from the qualified probe')
        output.rename(destination)
    print(result)


if __name__ == '__main__':
    main()
