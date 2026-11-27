# SPDX-License-Identifier: Apache-2.0
"""Exercise GCC Seed build paths with the pinned configure recorder and real cross tools."""

import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_gcc import configure_command, file_prefix_options, normalize_gcc_tools, path_leak_check, wrapper


def output(*command, cwd=None):
    return subprocess.check_output(command, cwd=cwd, text=True).strip()


def check_build(root, recorder, compilers, libgcc, readelf):
    source = root / 'src'
    build = root / 'build'
    sdk = root / 'sdk'
    stdcxx = root / 'stdcxx'
    for directory in (source, build, sdk, stdcxx):
        directory.mkdir(parents=True)

    configure = source / 'configure'
    configure.write_text(recorder)
    configure.chmod(0o755)
    options = ('--enable-languages=c,c++', '--prefix=/usr')
    recorded = output(*configure_command(source, build, options), cwd=build)
    if str(root) in recorded or str(root) not in output(configure, *options, cwd=build):
        raise RuntimeError('configure invocation did not preserve the portable argument record')

    compiled = {}
    prefix_maps = file_prefix_options(source, build, sdk, stdcxx)
    for suffix, compiler in compilers.items():
        frontend = build / f'compiler_{suffix}'
        wrapper(frontend, compiler, sdk, libgcc, file_prefix_maps=prefix_maps)
        probe = source / f'file_probe.{suffix}'
        probe.write_text('extern const char probe[];\nconst char probe[] = __FILE__;\n')
        mapped = build / (suffix + '.o')
        unmapped = build / ('old_' + suffix + '.o')
        for tool, obj in ((frontend, mapped), (compiler, unmapped)):
            subprocess.run([tool, '-O2', '-g', '-c', probe, '-o', obj], cwd=build, check=True)
        try:
            path_leak_check(unmapped, (root,))
        except RuntimeError:
            pass
        else:
            raise RuntimeError('the leaking object passed the Seed path check')
        path_leak_check(mapped, (root,))
        data = mapped.read_bytes()
        if f'/usr/src/gcc-16.2.0/file_probe.{suffix}'.encode() not in data:
            raise RuntimeError('the GCC source path did not use its intended mapping')
        if 'Advanced Micro Devices X86-64' not in output(readelf, '-h', mapped):
            raise RuntimeError('the probe was not built for XOS x86-64')
        compiled[suffix] = hashlib.sha256(data).hexdigest()
    return {'configure': recorded, 'objects': compiled}


def check_install_normalization(root, gcc, strip, objcopy):
    tools = root / 'usr/bin'
    tools.mkdir(parents=True)
    (root / 'usr/libexec/gcc/x86_64-elf/16.2.0').mkdir(parents=True)
    assembly = root / 'start.S'
    assembly.write_text(f'.file "{assembly}"\n.text\n.globl _start\n_start: ret\n')
    binary = tools / 'x86_64-elf-gcc'
    subprocess.run([gcc, '-nostdlib', '-static', '-no-pie', assembly, '-o', binary], check=True)
    assert str(assembly).encode() in binary.read_bytes()
    code = root / 'text.bin'
    subprocess.run([objcopy, '-O', 'binary', '-j', '.text', binary, code], check=True)
    before = code.read_bytes()
    with redirect_stdout(sys.stderr):
        normalize_gcc_tools(root, strip, (root,))
    subprocess.run([objcopy, '-O', 'binary', '-j', '.text', binary, code], check=True)
    assert before and code.read_bytes() == before
    path_leak_check(binary, (root,))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gcc-configure', type=Path, required=True,
                        help='top-level configure from the pinned GCC source archive')
    configure = parser.parse_args().gcc_configure.read_bytes()
    source = configure.decode()
    start = source.index('progname=$0\n# if PWD')
    end = source.index('# Find the build, host, and target systems.', start)
    recorder = '#!/bin/sh\n' + source[start:end] + 'printf "%s\\n" "$TOPLEVEL_CONFIGURE_ARGUMENTS"\n'
    compilers = {suffix: shutil.which('x86_64-elf-' + name)
                 for suffix, name in (('c', 'gcc'), ('cpp', 'g++'))}
    readelf = shutil.which('x86_64-elf-readelf')
    strip, objcopy = (shutil.which(f'x86_64-elf-{name}') for name in ('strip', 'objcopy'))
    if not all((*compilers.values(), readelf, strip, objcopy)):
        raise RuntimeError('the XOS x86_64-elf cross tools are required')
    libgcc = Path(output(compilers['c'], '-print-libgcc-file-name'))
    with TemporaryDirectory(prefix='xos_seed_build_paths_') as temp:
        root = Path(temp).resolve()
        first, second = (check_build(root / label, recorder, compilers, libgcc, readelf)
                         for label in ('first build', 'second build'))
        check_install_normalization(root, compilers['c'], strip, objcopy)
    if first != second:
        raise RuntimeError('configure metadata or mapped objects differed between build roots')
    print(json.dumps({
        'status': 'passed', 'compiler_version': output(compilers['c'], '-dumpfullversion'),
        'gcc_configure_sha256': hashlib.sha256(configure).hexdigest(), 'build_roots': 2,
        'unmapped_objects_rejected': 4, 'install_file_symbol_removed': True, **first,
    }, indent=2))


if __name__ == '__main__':
    main()
