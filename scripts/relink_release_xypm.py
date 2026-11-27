#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reproduce a released static program link from detached release materials."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from glibc_g1_probe import clean_build_environment
from xypm_format import confined, inspect_elf, load_json, require, sha_file

LINK_FLAGS = {'-static', '-no-pie', '-nostdlib', '-T', '-Wl,--build-id=none', '-Wl,-z,noexecstack',
              '-Wl,--gc-sections,--build-id=none,-z,noexecstack,-z,max-page-size=4096',
              '-Wl,-z,max-page-size=4096', '-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096', '-Wl,--start-group', '-Wl,--end-group'}
LIBC = 'sysroot/usr/lib/libc.a'
FORMAT = 'xos_release_xypm_relink_v1'
DASH_FORMAT = 'xos_release_dash_relink_v1'
MAKE_FORMAT = 'xos_release_gnu_make_relink_v1'
CPYTHON_FORMAT = 'xos_release_cpython_relink_v1'
DRIVERS = {'xypm': (FORMAT, 'g++'), 'dash': (DASH_FORMAT, 'gcc'), 'make': (MAKE_FORMAT, 'gcc'),
           'cpython': (CPYTHON_FORMAT, 'gcc')}


def relink(args):
    manifest_path = confined(args.materials, 'manifest.json')
    require(sha_file(manifest_path) == args.sha256, 'materials manifest differs')
    manifest = load_json(manifest_path)
    format_name, driver = DRIVERS[getattr(args, 'program', 'xypm')]
    require(manifest['format'] == format_name and set(manifest['tools']) == {driver, 'as', 'ld'},
            'unexpected materials receipt')
    files = {name: confined(args.materials, name) for name in manifest['files']}
    require(all(sha_file(path) == manifest['files'][name] for name, path in files.items()),
            'a materials file changed')
    tools = {}
    for name, expected in manifest['tools'].items():
        binary = shutil.which('x86_64-elf-' + name)
        require(binary is not None and sha_file(binary) == expected, 'link tool differs: ' + name)
        tools[name] = Path(binary).resolve(strict=True)
    if args.libc:
        replacement = args.libc.resolve(strict=True)
        with replacement.open('rb') as member:
            require(member.read(8) == b'!<arch>\n', 'expected a standalone replacement archive')
        require(sha_file(replacement) == args.libc_sha256, 'replacement archive digest differs')
        files[LIBC] = replacement
    flags = []
    for item in manifest['plan']:
        if isinstance(item, str):
            require(item in LINK_FLAGS, 'unexpected link flag')
            flags.append(item)
        else:
            name = item['file']
            require(name.startswith(('objects/', 'sysroot/')) and name in files, 'unexpected link input')
            flags.append(str(files[name]))
    output = args.output.resolve()
    require(not output.is_relative_to(args.materials.resolve()) and not args.output.is_symlink()
            and not output.exists(), 'choose absent output outside the materials')
    output.parent.mkdir(parents=True, exist_ok=True)
    env, _ = clean_build_environment(os.environ)
    with TemporaryDirectory(dir=output.parent) as directory:
        work = Path(directory)
        for name in ('as', 'ld'):
            (work / name).symlink_to(tools[name])
        elf = work / 'linked.elf'
        subprocess.run([tools[driver], '--sysroot=' + str(args.materials.resolve() / 'sysroot'),
                        '-B' + directory + '/', '-o', elf, *flags], check=True, env=env)
        inspect_elf(elf)
        digest = sha_file(elf)
        require((digest != manifest['reference']) if args.libc else (digest == manifest['reference']),
                'relink does not match the selected runtime')
        os.link(elf, output)
    print(digest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--program', choices=DRIVERS, default='xypm')
    parser.add_argument('--materials', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--libc', type=Path)
    parser.add_argument('--libc-sha256')
    args = parser.parse_args()
    if (args.libc is None) != (args.libc_sha256 is None):
        parser.error('--libc and --libc-sha256 must be supplied together')
    relink(args)


if __name__ == '__main__':
    main()
