#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build isolated multibyte newlib candidates; no SDK or vendored files are changed."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '4.6.0.20260123'
SOURCE_NAME = f'newlib-{VERSION}'
SOURCE_URL = f'https://sourceware.org/pub/newlib/{SOURCE_NAME}.tar.gz'
SOURCE_SHA256 = '6ff27e3bf022666f43f7802255be680eeff722ac181b1725d21e2e8318604ee3'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True,
                        help='new, nonexistent private directory for both profiles')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    if args.jobs < 1 or args.jobs > 64:
        parser.error('--jobs must be in 1..64')
    archive = args.archive.resolve(strict=True)
    if digest(archive) != SOURCE_SHA256:
        raise SystemExit('newlib archive does not match the frozen SHA256')
    work = args.output.resolve()
    if work.exists() or work.is_relative_to(ROOT / 'src') or work.is_relative_to(ROOT / 'localpilot'):
        raise SystemExit('output must be a new private directory outside src and localpilot')
    required = ['x86_64-elf-gcc', 'x86_64-elf-as', 'x86_64-elf-ld', 'make']
    selected = {name: shutil.which(name) for name in required}
    if any(path is None for path in selected.values()):
        raise SystemExit(f'missing build tool: {selected}')
    work.mkdir(parents=True)
    versions = {name: subprocess.check_output([path, '--version'], text=True).splitlines()[0]
                for name, path in selected.items()}
    receipt = {'status': 'building', 'source_url': SOURCE_URL, 'source_sha256': SOURCE_SHA256,
               'script_sha256': digest(Path(__file__)), 'tools': selected, 'tool_versions': versions,
               'commands': [], 'profiles': {},
               'note': 'Build candidate only; no XOS runtime or UTF-8 acceptance.'}
    receipt_path = work / 'receipt.json'
    try:
        with tarfile.open(archive) as source_archive:
            source_archive.extractall(work, filter='data')
        source = work / SOURCE_NAME
        if not (source / 'configure').is_file():
            raise RuntimeError('archive does not contain expected configure script')
        tools = work / 'target_tools'
        tools.mkdir()
        for name in ('as', 'ld'):
            (tools / name).symlink_to(selected['x86_64-elf-' + name])
        for profile in ('single', 'threaded'):
            profile_dir = work / profile
            build = profile_dir / 'build'
            prefix = profile_dir / 'prefix'
            build.mkdir(parents=True)
            env = os.environ.copy()
            env.pop('COMPILER_PATH', None)
            compiler = shlex.quote(selected['x86_64-elf-gcc'])
            tool_prefix = shlex.quote(str(tools) + '/')
            env.update(CC_FOR_TARGET=f'{compiler} -B{tool_prefix}',
                       CCAS_FOR_TARGET=f'{compiler} -B{tool_prefix}',
                       CFLAGS_FOR_TARGET='-O2 -g -mno-red-zone' +
                       (' -D__DYNAMIC_REENT__' if profile == 'threaded' else ''))
            options = ['--target=x86_64-elf', f'--prefix={prefix}', '--disable-multilib',
                       '--disable-newlib-supplied-syscalls', '--disable-libgloss',
                       '--enable-newlib-mb', '--disable-newlib-io-long-double',
                       '--disable-newlib-io-long-long', '--disable-newlib-io-c99-formats',
                       '--disable-newlib-io-pos-args']
            if profile == 'threaded':
                options += ['--enable-newlib-retargetable-locking',
                            '--enable-newlib-global-atexit', '--enable-newlib-global-stdio-streams']
            profile_info = {'status': 'building', 'environment': {k: env[k] for k in
                            ('CC_FOR_TARGET', 'CCAS_FOR_TARGET', 'CFLAGS_FOR_TARGET')}}
            receipt['profiles'][profile] = profile_info
            for command, log in (([str(source / 'configure'), *options], 'configure.log'),
                                 ([selected['make'], f'-j{args.jobs}'], 'make.log'),
                                 ([selected['make'], 'install'], 'install.log')):
                receipt['commands'].append({'profile': profile, 'argv': command, 'cwd': str(build),
                                            'log': str(profile_dir / log)})
                receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
                with (profile_dir / log).open('w') as output:
                    subprocess.run(command, cwd=build, env=env, stdout=output,
                                   stderr=subprocess.STDOUT, check=True)
            include = prefix / 'x86_64-elf/include/newlib.h'
            if '#define _MB_CAPABLE 1' not in include.read_text():
                raise RuntimeError(f'{profile} did not produce _MB_CAPABLE')
            profile_info['artifacts'] = {str(p.relative_to(prefix)): digest(p)
                                         for p in sorted(prefix.rglob('*')) if p.is_file()}
            profile_info['status'] = 'built_unverified'
            # The threading SDK builder consumes prefix.parent/receipt.json.
            (profile_dir / 'receipt.json').write_text(json.dumps({
                'status': 'built_unverified', 'source_sha256': SOURCE_SHA256,
                'profile': profile, 'script_sha256': receipt['script_sha256'],
                'environment': profile_info['environment'],
                'commands': [item for item in receipt['commands'] if item['profile'] == profile],
                'artifacts': profile_info['artifacts']}, indent=2) + '\n')
        receipt['status'] = 'built_unverified'
    except Exception as error:
        receipt['status'] = 'failed'
        receipt['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    print(receipt_path)


if __name__ == '__main__':
    main()
