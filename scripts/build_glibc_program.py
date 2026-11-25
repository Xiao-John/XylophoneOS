#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compile and statically link a C program against the isolated XOS glibc SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess

from glibc_g1_probe import clean_build_environment, tool_identity


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_elf(path):
    data = path.read_bytes()
    if data[:7] != b'\x7fELF\x02\x01\x01':
        raise RuntimeError('output is not a little-endian ELF64 image')
    kind, machine = struct.unpack_from('<HH', data, 16)
    if kind != 2 or machine != 62:
        raise RuntimeError('output must be an x86-64 ET_EXEC image')
    offset = struct.unpack_from('<Q', data, 32)[0]
    entry_size, count = struct.unpack_from('<HH', data, 54)
    if entry_size != 56 or offset + count * entry_size > len(data):
        raise RuntimeError('invalid ELF program headers')
    headers = []
    for i in range(count):
        item = struct.unpack_from('<IIQQQQQQ', data, offset + i * entry_size)
        typ, flags, file_offset, address, _, file_size, memory_size, alignment = item
        if typ in (2, 3):
            raise RuntimeError('dynamic interpreter/loading is outside this SDK profile')
        if typ == 1 and (flags & 3 == 3 or file_size > memory_size
                         or file_offset + file_size > len(data)):
            raise RuntimeError('invalid or writable-executable load segment')
        headers.append({'type': typ, 'flags': flags, 'virtual_address': address,
                        'file_size': file_size, 'memory_size': memory_size,
                        'alignment': alignment})
    return headers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--source', type=Path, action='append', required=True)
    parser.add_argument('--define', action='append', default=[], metavar='NAME[=VALUE]')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--diagnostic', action='store_true',
                        help='allow an incomplete SDK; output is unqualified diagnostic evidence')
    args = parser.parse_args()
    if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:=[^\r\n\x00]*)?', item)
           for item in args.define):
        parser.error('invalid preprocessor definition')
    sdk = args.sdk.resolve(strict=True)
    sources = [path.resolve(strict=True) for path in args.source]
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        parser.error('output must be a new ELF path')
    env, removed = clean_build_environment(os.environ)
    env['LC_ALL'] = 'C'
    compiler = tool_identity('x86_64-elf-gcc')
    if not compiler['available']:
        parser.error('x86_64-elf-gcc is required')
    manifest_path = sdk.parent / 'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    if not args.diagnostic:
        if manifest.get('status') != 'static_sdk_built':
            parser.error('SDK manifest is not a completed static build')
        if manifest['tools']['x86_64-elf-gcc']['sha256'] != compiler['sha256']:
            parser.error('compiler differs from the SDK build')
        for relative, expected in manifest['artifacts'].items():
            path = sdk / relative
            if not path.is_file() or sha(path) != expected:
                parser.error('SDK artifact mismatch: ' + relative)
    work = output.parent / (output.name + '.build')
    work.mkdir(parents=True, exist_ok=False)
    report = {'status': 'building', 'diagnostic': args.diagnostic,
              'sdk_manifest_sha256': sha(manifest_path) if manifest_path.is_file() else None,
              'compiler': compiler, 'sanitized_environment': removed,
              'sources': {str(path): sha(path) for path in sources}, 'steps': [],
              'guest_qualification': 'not_run'}

    def save():
        (work / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')

    def run(name, command):
        log = work / (name + '.log')
        with log.open('w') as stream:
            result = subprocess.run(command, env=env, stdout=stream,
                                    stderr=subprocess.STDOUT)
        report['steps'].append({'name': name, 'command': command,
                                'exit_code': result.returncode, 'log_sha256': sha(log)})
        save()
        if result.returncode:
            raise RuntimeError(name + ' failed; see ' + str(log))

    try:
        private_headers = sdk / 'usr/lib/compiler-include'
        if args.diagnostic and not private_headers.is_dir():
            private_headers = Path(subprocess.check_output(
                [compiler['path'], '-print-file-name=include'], env=env, text=True).strip())
        flags = [compiler['path'], '--sysroot=' + str(sdk), '-O2', '-g',
                 '-std=gnu11', '-mno-red-zone', '-fno-pie', '-fno-omit-frame-pointer',
                 '-fno-builtin',
                 '-ftls-model=local-exec', '-nostdinc',
                 '-isystem', str(sdk / 'usr/include'), '-isystem', str(private_headers)]
        flags.extend('-D' + item for item in args.define)
        objects = []
        for i, source in enumerate(sources):
            obj = work / ('program_' + str(i) + '.o')
            run('compile-' + str(i), flags + ['-c', str(source), '-o', str(obj)])
            objects.append(str(obj))
        lib = sdk / 'usr/lib'
        unwind = [str(lib / 'libgcc_eh.a')] if (lib / 'libgcc_eh.a').is_file() else []
        run('link', [compiler['path'], '--sysroot=' + str(sdk), '-static', '-no-pie',
                     '-nostdlib', '-Wl,--build-id=none', '-Wl,-z,noexecstack',
                     '-Wl,-z,max-page-size=4096',
                     '-Wl,-T,' + str(sdk / 'user.ld'), '-o', str(output),
                     str(lib / 'xos_start.o'), str(lib / 'crti.o'),
                     str(lib / 'crtbegin.o'), str(lib / 'xos_start_c.o'), *objects,
                     '-Wl,--start-group', str(lib / 'libc.a'), str(lib / 'libm.a'),
                     str(lib / 'libgcc.a'), *unwind, '-Wl,--end-group',
                     str(lib / 'crtend.o'), str(lib / 'crtn.o')])
        report['program_headers'] = verify_elf(output)
        if any(sha(path) != report['sources'][str(path)] for path in sources):
            raise RuntimeError('source changed during compilation')
        report['elf_sha256'] = sha(output)
        report['status'] = 'diagnostic_linked' if args.diagnostic else 'static_program_linked'
        save()
    except BaseException as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        save()
        raise


if __name__ == '__main__':
    main()
