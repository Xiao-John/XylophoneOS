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
    commands, objects, sources = [], [], []

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
              'leak_sanitizer': 'not_run', 'commands': commands}
    try:
        for name in ['xos_file_runtime', 'xos_file_directory', 'xos_file_positioned']:
            source = overlay / (name + '.c')
            obj = output / (name + '.o')
            run([os.getenv('CC', 'gcc'), '-std=c11', '-DXOS_GLIBC_FILE_TEST', *flags, *includes,
                 '-Wall', '-Wextra', '-Werror', '-Wconversion', '-Wshadow', '-c', str(source), '-o', str(obj)], name)
            objects.append(obj)
            sources.append(source)
        for name, relative in [('fatfs', 'src/third_party/fatfs/ff.c'),
                               ('unicode', 'src/user/services/fatfs_unicode.cpp'),
                               ('client', 'src/user/sdk/file_client.cpp'),
                               ('text', 'src/user/sdk/text.cpp')]:
            source = ROOT / relative
            obj = output / (name + '.o')
            run([os.getenv('CXX', 'g++'), '-std=c++20', *flags, *includes, '-c', str(source), '-o', str(obj)], name)
            objects.append(obj)
            sources.append(source)
        fixture = ROOT / 'tests/fixtures/glibc_g3/files_extra_service.cpp'
        binary = output / 'files_extra'
        run([os.getenv('CXX', 'g++'), '-std=c++20', *flags, *includes,
             str(fixture), *map(str, objects), '-Wl,--gc-sections', '-o', str(binary)], 'link')
        disk = output / 'private.img'
        disk.write_bytes(make_image())
        result = run([str(binary), str(disk)], 'run')
        disk.unlink()
        print(result, end='')
        sources += [fixture, Path(__file__).resolve(), ROOT / 'src/user/services/files.cpp',
                    ROOT / 'src/shared/include/xos/file_abi.hpp', ROOT / 'src/user/include/xos/file_client.hpp',
                    ROOT / 'tests/fixtures/file_semantics/file_semantics.cpp']
        sources += list(overlay.glob('xos_file*.h')) + [overlay / 'dirstream.h', overlay / 'bits/dirent.h']
        report.update(status='passed', output=result,
                      sources={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in sorted(set(sources))})
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
