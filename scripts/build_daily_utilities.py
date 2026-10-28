# SPDX-License-Identifier: Apache-2.0
"""Build the explicit DU1 candidates against an explicitly selected XOS SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from xos_app import tree_receipt
from xypm_format import canonical, inspect_elf, load_json, require, sha_file

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / 'src/ports/sbase'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True, help='pinned sbase source checkout')
    parser.add_argument('--output-dir', type=Path, required=True, help='new, empty output directory')
    args = parser.parse_args()
    try:
        sdk = args.sdk.resolve(strict=True)
        source = args.source.resolve(strict=True)
        lock = load_json(PORT / 'source_lock.json')
        for name, expected in lock['files'].items():
            require(sha_file(source / name) == expected, 'upstream source mismatch: ' + name)
        registry = load_json(PORT / 'daily_utilities.json')
        require(registry['format_version'] == 1, 'unknown utility manifest')
        names = [item['name'] for item in registry['tools']]
        require(len(names) == len(set(names)) and all(name.isascii() and name.isalpha() for name in names), 'invalid tool names')
        digest, _ = tree_receipt(sdk)
        compiler = shutil.which(os.environ.get('XOS_CC', 'x86_64-elf-gcc'))
        require(compiler is not None, 'cross compiler not found')
        target = subprocess.check_output([compiler, '-dumpmachine'], text=True).strip()
        version = subprocess.check_output([compiler, '-dumpfullversion'], text=True).strip()
        require(target == 'x86_64-elf', 'wrong compiler target')
        for variable in ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH',
                         'LIBRARY_PATH', 'COMPILER_PATH', 'GCC_EXEC_PREFIX'):
            require(not os.environ.get(variable), 'ambient compiler injection variable: ' + variable)
        libgcc = subprocess.check_output([compiler, '-print-libgcc-file-name'], text=True).strip()
        out = args.output_dir.resolve()
        out.mkdir(parents=True, exist_ok=False)
        tools = []
        registry_hash = sha_file(PORT / 'daily_utilities.json')
        builder_hash = sha_file(__file__)
        source_hashes = {}
        for item in registry['tools']:
            name = item['name']
            src = PORT / item['source']
            require(src.is_file() and not src.is_symlink() and src.resolve().is_relative_to(PORT.resolve()), 'bad source path')
            source_hashes[name] = sha_file(src)
            output = out / name
            command = [compiler, '-O2', '-mno-red-zone', '-fno-pie', '-fno-pic', '-fno-stack-protector',
                       '-idirafter', str(sdk / 'include'), '-nostdlib', '-static', '-no-pie',
                       '-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096', '-T', str(sdk / 'user.ld'),
                       str(sdk / 'crt0_posix.o'), str(src), '-Wl,--start-group',
                       str(sdk / 'lib/libxos.a'), str(sdk / 'lib/libxos_loader.a'),
                       str(sdk / 'lib/libc.a'), str(sdk / 'lib/libm.a'), libgcc, '-Wl,--end-group', '-o', str(output)]
            subprocess.run(command, check=True)
            layout = inspect_elf(output)
            require(sha_file(src) == source_hashes[name], 'source changed during build: ' + name)
            tools.append({**item, 'source_sha256': source_hashes[name], 'elf_sha256': sha_file(output),
                          'size': output.stat().st_size, 'guest_path': '/usr/bin/' + name, 'elf_layout': layout})
        require(tree_receipt(sdk)[0] == digest, 'SDK changed during build')
        require(sha_file(PORT / 'daily_utilities.json') == registry_hash and sha_file(__file__) == builder_hash,
                'registry or builder changed during build')
        for item in registry['tools']:
            require(sha_file(PORT / item['source']) == source_hashes[item['name']], 'source changed during build')
        manifest = {'status': 'built_not_run', 'sdk_tree_sha256': digest, 'sdk_manifest_sha256': sha_file(sdk / 'manifest.json'),
                    'compiler': {'target': target, 'version': version, 'sha256': sha_file(compiler)},
                    'libgcc_sha256': sha_file(libgcc), 'source_commit': lock['commit'],
                    'registry_sha256': registry_hash,
                    'builder_sha256': builder_hash, 'tools': tools}
        (out / 'manifest.json').write_bytes(canonical(manifest))
        print(json.dumps(manifest, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print('daily-utilities: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
