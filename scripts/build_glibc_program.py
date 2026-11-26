#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compile and statically link a C or C++ program against the isolated XOS glibc SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess

from glibc_g1_probe import clean_build_environment, tool_identity
from xypm_format import load_json
from xypm_sdk_profile import metadata_snapshot, verify_profile


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def project_dependencies(depfile, project, inputs):
    target, _, dependencies = depfile.read_text().replace('\\\n', '').partition(':')
    if target != 'xos_object':
        raise RuntimeError('invalid compiler dependency record')
    for escaped in re.findall(r'(?:\\.|[^\s\\])+', dependencies):
        name = re.sub(r'\\(.)', r'\1', escaped).replace('$$', '$')
        path = Path(name).resolve(strict=True)
        if not path.is_relative_to(project) or path.relative_to(project).as_posix() not in inputs:
            raise RuntimeError('application dependency is outside the recorded project inputs: ' + name)


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
    parser.add_argument('--profile', type=Path, help='explicit glibc candidate from create_xypm_profile.py')
    parser.add_argument('--cxx', action='store_true', help='build C++ using a C++ candidate profile')
    parser.add_argument('--source', type=Path, action='append', required=True)
    parser.add_argument('--include-dir', type=Path, action='append', default=[])
    parser.add_argument('--project-inputs', type=Path, help='build receipt inputs relative to the current project directory')
    parser.add_argument('--define', action='append', default=[], metavar='NAME[=VALUE]')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--diagnostic', action='store_true',
                        help='allow an incomplete SDK; output is unqualified diagnostic evidence')
    args = parser.parse_args()
    if args.cxx and not args.profile:
        parser.error('--cxx requires a glibc C++ candidate profile')
    if args.diagnostic and args.profile:
        parser.error('--diagnostic and --profile are mutually exclusive')
    if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:=[^\r\n\x00]*)?', item)
           for item in args.define):
        parser.error('invalid preprocessor definition')
    if args.profile and (args.sdk.name != 'sysroot' or args.sdk.is_symlink()):
        parser.error('--profile requires the SDK build sysroot directory')
    sdk = args.sdk.resolve(strict=True)
    sources = [path.resolve(strict=True) for path in args.source]
    includes = [path.resolve(strict=True) for path in args.include_dir]
    if any(not path.is_dir() for path in includes):
        parser.error('--include-dir must name a directory')
    inputs = load_json(args.project_inputs) if args.project_inputs else None
    if args.output.is_symlink():
        parser.error('output must be a new ELF path')
    output = args.output.resolve()
    if output.exists() or output.is_symlink():
        parser.error('output must be a new ELF path')
    if args.profile and (output == sdk.parent or sdk.parent in output.parents):
        parser.error('output must be outside the SDK build')
    env, removed = clean_build_environment(os.environ)
    env['LC_ALL'] = 'C'
    compiler_name = 'x86_64-elf-g++' if args.cxx else 'x86_64-elf-gcc'
    manifest_path = sdk.parent / 'manifest.json'
    candidate = None
    binutils = {}
    if args.profile:
        try:
            candidate = load_json(args.profile)
            binding = verify_profile(candidate, 'glibc', args.sdk.parent)
            expected_sha = candidate['sdk_binding']['sdk_manifest_sha256']
            manifest, _ = metadata_snapshot(manifest_path, expected_sha)
            if args.cxx and 'cxx_runtime' not in candidate['features']:
                parser.error('--cxx requires the candidate cxx_runtime feature')
            suffixes = ('.cpp', '.cc', '.cxx') if args.cxx else ('.c',)
            if any(source.suffix not in suffixes for source in sources):
                parser.error('source file extension does not match the selected language')
            for name in ('as', 'ld'):
                tool_name = 'x86_64-elf-' + name
                tool = tool_identity(tool_name)
                if not tool['available'] or tool['sha256'] != manifest['tools'][tool_name]['sha256']:
                    parser.error(tool_name + ' differs from the SDK build')
                binutils[name] = tool
        except (OSError, ValueError, KeyError, TypeError) as error:
            parser.exit(1, 'glibc profile: ' + str(error) + '\n')
    elif not args.diagnostic:
        manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
        if manifest.get('status') != 'static_sdk_built':
            parser.error('SDK manifest is not a completed static build')
        for relative, expected in manifest['artifacts'].items():
            path = sdk / relative
            if not path.is_file() or sha(path) != expected:
                parser.error('SDK artifact mismatch: ' + relative)
    compiler = tool_identity(compiler_name)
    if not compiler['available']:
        parser.error(compiler_name + ' is required')
    if not args.diagnostic and manifest['tools'][compiler_name]['sha256'] != compiler['sha256']:
        parser.error('compiler differs from the SDK build')
    work = output.parent / (output.name + '.build')
    work.mkdir(parents=True, exist_ok=False)
    report = {'status': 'building', 'diagnostic': args.diagnostic, 'language': 'c++' if args.cxx else 'c',
              'builder_sha256': sha(Path(__file__)),
              'sdk_manifest_sha256': sha(manifest_path) if manifest_path.is_file() else None,
              'compiler': compiler, 'sanitized_environment': removed,
              'sources': {str(path): sha(path) for path in sources}, 'steps': [],
              'guest_qualification': 'not_run'}
    if candidate is not None:
        report['profile_binding'] = binding
        report['binutils'] = binutils

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
        driver = [compiler['path'], '--sysroot=' + str(sdk)]
        if binutils:
            tool_dir = work / 'tools'
            tool_dir.mkdir()
            for name, tool in binutils.items():
                (tool_dir / name).symlink_to(tool['path'])
            driver.append('-B' + str(tool_dir) + '/')
        flags = driver + ['-O2', '-g', '-mno-red-zone', '-fno-pie', '-fno-omit-frame-pointer',
                          '-ftls-model=local-exec', '-nostdinc']
        if args.cxx:
            flags += ['-std=gnu++20', '-nostdinc++', '-fno-pic', '-D_GNU_SOURCE=1']
            for relative in candidate['sdk_binding']['cxx_runtime']['include_directories']:
                flags += ['-isystem', str(sdk / relative)]
        else:
            flags += ['-std=gnu11', '-fno-builtin']
        flags += ['-isystem', str(sdk / 'usr/include'), '-isystem', str(private_headers)]
        for include in includes:
            flags += ['-I', str(include)]
        flags.extend('-D' + item for item in args.define)
        objects = []
        for i, source in enumerate(sources):
            obj = work / ('program_' + str(i) + '.o')
            compile_flags = flags
            if inputs is not None:
                depfile = work / ('program_' + str(i) + '.d')
                compile_flags = flags + ['-MMD', '-MF', str(depfile), '-MT', 'xos_object']
            run('compile-' + str(i), compile_flags + ['-c', str(source), '-o', str(obj)])
            if inputs is not None:
                project_dependencies(depfile, Path.cwd(), inputs)
            objects.append(str(obj))
        lib = sdk / 'usr/lib'
        unwind = [str(lib / 'libgcc_eh.a')] if (lib / 'libgcc_eh.a').is_file() else []
        cxx_libraries = [str(lib / name) for name in ('libstdc++.a', 'libsupc++.a')] if args.cxx else []
        terminal = [str(lib / 'libxos_terminal.a')]
        if candidate is not None and 'usr/lib/libxos_terminal.a' not in candidate['sdk_binding']['link_artifacts']:
            terminal = []
        linked = work / 'program.elf'
        run('link', driver + ['-static', '-no-pie',
                     '-nostdlib', '-Wl,--build-id=none', '-Wl,-z,noexecstack',
                     '-Wl,-z,max-page-size=4096',
                     '-T', str(sdk / 'user.ld'), '-o', str(linked),
                     str(lib / 'xos_start.o'), str(lib / 'crti.o'),
                     str(lib / 'crtbegin.o'), str(lib / 'xos_start_c.o'), *objects,
                     '-Wl,--start-group', *cxx_libraries, str(lib / 'libc.a'), str(lib / 'libm.a'),
                     *terminal,
                     str(lib / 'libgcc.a'), *unwind, '-Wl,--end-group',
                     str(lib / 'crtend.o'), str(lib / 'crtn.o')])
        report['program_headers'] = verify_elf(linked)
        if (sha(Path(__file__)) != report['builder_sha256']
                or any(sha(path) != report['sources'][str(path)] for path in sources)):
            raise RuntimeError('source changed during compilation')
        if candidate is not None:
            if (verify_profile(load_json(args.profile), 'glibc', args.sdk.parent) != binding
                    or any(sha(Path(t['path'])) != t['sha256'] for t in (compiler, *binutils.values()))):
                raise RuntimeError('profile or toolchain changed during compilation')
        report['elf_sha256'] = sha(linked)
        os.link(linked, output)
        linked.unlink()
        report['status'] = 'diagnostic_linked' if args.diagnostic else 'static_program_linked'
        save()
    except BaseException as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        save()
        raise


if __name__ == '__main__':
    main()
