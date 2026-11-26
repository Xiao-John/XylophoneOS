#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real positioned I/O and directories across glibc/SDK/files/FatFs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from make_work_disk import make_image

NATIVE_SOURCES = (
    ('fatfs', 'src/third_party/fatfs/ff.c'),
    ('unicode', 'src/user/services/fatfs_unicode.cpp'),
    ('elf', 'src/user/loader/elf.cpp'),
    ('client', 'src/user/sdk/file_client.cpp'),
    ('text', 'src/user/sdk/text.cpp'),
    ('terminal_support', 'src/ports/glibc/terminal_support.cpp'),
    ('terminal_client', 'src/user/sdk/terminal_client.cpp'),
)


def source_snapshot():
    overlay = ROOT / 'src/ports/glibc/sysdeps/xos'
    sources = [overlay / (name + '.c') for name in
               ('xos_file_runtime', 'xos_file_directory', 'xos_file_positioned')]
    sources += [ROOT / name for _, name in NATIVE_SOURCES]
    sources += [ROOT / name for name in
                ('src/user/services/files.cpp', 'tests/fixtures/glibc_g3/files_extra_service.cpp',
                 'tests/fixtures/file_semantics/file_semantics.cpp', 'scripts/make_work_disk.py')]
    sources += [Path(__file__).resolve()]
    sources += list(overlay.rglob('*.h')) + list((ROOT / 'src/third_party/fatfs').glob('*.h'))
    sources += [path for name in ('src/shared/include/xos', 'src/user/include/xos')
                for path in (ROOT / name).rglob('*.hpp')]
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(set(sources))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    overlay = ROOT / 'src/ports/glibc/sysdeps/xos'
    flags = ['-D_GNU_SOURCE', '-O1', '-g', '-ffunction-sections', '-fdata-sections']
    # Native SDK xos/ headers are needed, while libc headers come from the
    # host + glibc overlay. Do not import the newlib-facing dirent.h shim.
    includes = ['-I', str(overlay), '-I', str(ROOT / 'src/shared/include'),
                '-I', str(ROOT / 'src/third_party/fatfs'), '-idirafter', str(ROOT / 'src/user/include')]
    if args.sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
    commands, objects = [], []

    def run(command, name):
        commands.append(list(map(str, command)))
        result = subprocess.run(command, text=True, capture_output=True, timeout=120,
                                env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
        (output / (name + '.log')).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f'{name}: exit {result.returncode}\n{result.stdout}{result.stderr}')
        return result.stdout

    report = {'status': 'failed', 'kernel_transport': 'simulated', 'guest': 'not_run_by_this_runner',
              'sanitizers': ['address', 'undefined'] if args.sanitize else [],
              'leak_sanitizer': 'not_run', 'commands': commands, 'source_snapshot_verified': False}
    try:
        # Freeze all translation units, repository headers and image-generation
        # inputs before the first compiler invocation. Keep these original
        # digests in failed reports as well as successful qualifications.
        report['sources'] = source_snapshot()
        for name in ['xos_file_runtime', 'xos_file_directory', 'xos_file_positioned']:
            source = overlay / (name + '.c')
            obj = output / (name + '.o')
            run([os.getenv('CC', 'gcc'), '-std=c11', '-DXOS_GLIBC_FILE_TEST', *flags, *includes,
                 '-Wall', '-Wextra', '-Werror', '-Wconversion', '-Wshadow', '-c', str(source), '-o', str(obj)], name)
            objects.append(obj)
        for name, relative in NATIVE_SOURCES:
            source = ROOT / relative
            obj = output / (name + '.o')
            run([os.getenv('CXX', 'g++'), '-std=c++20', *flags, *includes, '-c', str(source), '-o', str(obj)], name)
            objects.append(obj)
        fixture = ROOT / 'tests/fixtures/glibc_g3/files_extra_service.cpp'
        binary = output / 'files_extra'
        run([os.getenv('CXX', 'g++'), '-std=c++20', *flags, *includes,
             str(fixture), *map(str, objects), '-Wl,--gc-sections', '-o', str(binary)], 'link')
        disk = output / 'private.img'
        disk.write_bytes(make_image())
        result = run([str(binary), str(disk)], 'run')
        disk.unlink()
        current_sources = source_snapshot()
        if current_sources != report['sources']:
            report['sources_after'] = current_sources
            raise RuntimeError('source inputs changed during qualification')
        report.update(status='passed', output=result, source_snapshot_verified=True)
        print(result, end='')
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
