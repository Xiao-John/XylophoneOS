#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Replay a released CPython static link and the bound debug-stripping step."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from glibc_g1_probe import clean_build_environment
from package_cpython_glibc import loaded_image
from relink_release_xypm import CPYTHON_FORMAT, relink as link_debug
from xypm_format import confined, inspect_elf, load_json, require, sha_file


def relink(args):
    manifest_path = confined(args.materials, 'manifest.json')
    require(sha_file(manifest_path) == args.sha256, 'materials manifest differs')
    manifest = load_json(manifest_path)
    require(manifest['format'] == CPYTHON_FORMAT, 'wrong CPython materials format')
    interpreter = manifest['interpreter']
    objcopy = shutil.which('x86_64-elf-objcopy')
    require(objcopy is not None and sha_file(objcopy) == interpreter['objcopy_sha256'],
            'CPython strip tool differs from the release')
    output = args.output.resolve()
    require(not output.exists() and not args.output.is_symlink() and not output.is_relative_to(args.materials.resolve()),
            'choose new output outside the materials')
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as folder:
        work = Path(folder)
        debug = work / 'debug.elf'
        link_debug(argparse.Namespace(program='cpython', materials=args.materials, sha256=args.sha256,
                                     output=debug, libc=args.libc, libc_sha256=args.libc_sha256))
        runtime = work / 'runtime.elf'
        env, _ = clean_build_environment(os.environ)
        subprocess.run([objcopy, '--strip-debug', debug, runtime], env=env, check=True)
        layout = inspect_elf(debug)
        require(layout['static_tls'] and layout == inspect_elf(runtime)
                and loaded_image(debug.read_bytes()) == loaded_image(runtime.read_bytes()),
                'debug stripping changed the loaded interpreter')
        digest = sha_file(runtime)
        if args.libc is None:
            require(digest == interpreter['sha256'] and runtime.stat().st_size == interpreter['bytes'],
                    'CPython runtime differs from the released XPK')
        else:
            require(digest != interpreter['sha256'], 'replacement libc did not change the CPython runtime')
        os.link(runtime, output)
    print(digest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('materials', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--libc', type=Path)
    parser.add_argument('--libc-sha256')
    args = parser.parse_args()
    if (args.libc is None) != (args.libc_sha256 is None):
        parser.error('--libc and --libc-sha256 must be supplied together')
    relink(args)


if __name__ == '__main__':
    main()
