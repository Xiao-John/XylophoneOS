#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the pinned installed DHCP/TLS dynamic GNU acceptance program.

Uses the existing public startup closure and identity helpers. TLS implementation
objects are PIC and use only the selected shared GNU libc. No C++ standard library
or new dynamic-linker interface is added.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from dynamic_artifacts import INTERPRETER, digest, generation_record, write_note
from installed_dynamic_tls_support import build_support
from glibc_g1_probe import clean_build_environment, tool_identity
from xypm_sdk_profile import inspect_sdk, relative_file, metadata_snapshot, sdk_snapshot

repository_root = Path(__file__).resolve().parents[1]
runtime_path = '/usr/lib/xos/glibc_dynamic_v1'


from build_dynamic_program import inspect_native_sdk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('sdk-build', 'native-sdk', 'runtime-build', 'source', 'tls-archive', 'certificates', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('sdk-manifest-sha256', 'sdk-tree-sha256', 'native-sdk-manifest-sha256', 'native-sdk-tree-sha256'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--generation-id', type=int, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', args.name):
        parser.error('name must be a bounded canonical native component')
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        parser.error('output must be a new directory')
    sdk = args.sdk_build.resolve(strict=True)
    native = args.native_sdk.resolve(strict=True)
    runtime = args.runtime_build.resolve(strict=True)
    c_binding = inspect_sdk('glibc', sdk)['binding']
    native_binding = inspect_native_sdk(native)
    for binding, expected_manifest, expected_tree in (
        (c_binding, args.sdk_manifest_sha256, args.sdk_tree_sha256),
        (native_binding, args.native_sdk_manifest_sha256, args.native_sdk_tree_sha256)):
        if binding['sdk_manifest_sha256'] != expected_manifest or binding['sdk_tree_sha256'] != expected_tree:
            raise ValueError('independent expected SDK manifest/full-tree anchor mismatch')
    metadata = json.loads((runtime / 'manifest.json').read_bytes())
    if (metadata.get('status') != 'public_runtime_built_not_run' or not metadata.get('public_startup')
            or metadata['sdk_binding'] != c_binding):
        raise ValueError('the selected runtime is not the matching public GNU composition')
    for name, expected in metadata['artifacts'].items():
        if digest(relative_file(runtime, name)) != expected:
            raise ValueError('runtime artifact changed: ' + name)
    c_snapshot = runtime / 'sdk_snapshot'
    if inspect_sdk('glibc', c_snapshot)['binding'] != c_binding:
        raise ValueError('the runtime SDK snapshot differs from the independent full anchor')
    original_native = native
    output.mkdir(parents=True)
    native = output / 'native_sdk_snapshot'
    shutil.copytree(original_native, native, symlinks=False)
    if (inspect_native_sdk(native) != native_binding
            or inspect_native_sdk(original_native) != native_binding):
        raise ValueError('native SDK changed before/after complete snapshot')
    sysroot = c_snapshot / 'sysroot'
    env, removed = clean_build_environment(os.environ)
    env['LC_ALL'] = 'C'
    tools = {name: tool_identity('x86_64-elf-' + name) for name in ('gcc', 'g++', 'ld', 'objcopy', 'readelf', 'ar', 'ranlib')}
    c_metadata = json.loads((sdk / 'manifest.json').read_bytes())
    for name, tool in tools.items():
        if tool.get('sha256') != c_metadata['tools']['x86_64-elf-' + name]['sha256']:
            raise ValueError('selected build tool differs from the anchored SDK')
    source = args.source.resolve(strict=True)
    inputs = {str(source): digest(source), str(runtime / 'manifest.json'): digest(runtime / 'manifest.json')}
    for path in sorted((source.parent).glob('*.h*')):
        inputs[str(path)] = digest(path)
    bootstrap_source = repository_root / 'src/user/loader/dynamic/bootstrap.cpp'
    for path in (bootstrap_source, repository_root / 'src/user/loader/dynamic/startup.hpp',
                 Path(__file__), repository_root / 'scripts/dynamic_artifacts.py', repository_root / 'scripts/dynamic_preflight.cpp',
                 repository_root / 'scripts/build_dynamic_program.py', repository_root / 'scripts/installed_dynamic_tls_support.py'):
        inputs[str(path)] = digest(path)
    report = {'status': 'building', 'public_startup': True, 'guest_qualification': 'not_run',
        'name': args.name, 'generation_id': args.generation_id, 'native_abi': metadata['native_abi'],
        'sdk_binding': c_binding, 'native_sdk_binding': native_binding, 'tools': tools,
        'commands': {}, 'inputs': inputs, 'sanitized_environment': removed}

    def save():
        (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')

    def run(label, arguments):
        command = list(map(str, arguments))
        report['commands'][label] = command
        with (output / (label + '.log')).open('w') as log:
            result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        save()
        if result.returncode:
            raise RuntimeError(label + ' failed; see ' + str(output / (label + '.log')))

    try:
        cc, cxx, ld, objcopy = (tools[name]['path'] for name in ('gcc', 'g++', 'ld', 'objcopy'))
        flags = ['--sysroot=' + str(sysroot), '-O2', '-mno-red-zone', '-nostdinc',
            '-isystem', sysroot / 'usr/include', '-isystem', sysroot / 'usr/lib/compiler-include',
            '-Wall', '-Wextra', '-Werror', '-Wa,--noexecstack', '-Werror=trampolines', '-I', source.parent]
        for name, role in (('main', 3), ('bootstrap', 1), ('library', 4)):
            assembly, obj = output / (name + '_identity.S'), output / (name + '_identity.o')
            write_note(assembly, metadata['native_abi'], role)
            run('identity-' + name, [cc, '-c', assembly, '-o', obj])
        gnu, crt = runtime / 'gnu', runtime / 'pic_crt/target/libgcc'
        payload = output / 'payload'
        payload.mkdir()
        run('strip-libc', [objcopy, '--strip-debug', gnu / 'libc.so', payload / 'libc.so.0.1'])
        run('strip-interpreter', [objcopy, '--strip-debug', gnu / 'elf/ld.so', payload / 'ld_xos_x86_64.so.1'])
        libraries = [(payload / 'libc.so.0.1', runtime_path + '/libc.so.0.1')]
        extra, app_libraries = build_support(args.tls_archive.resolve(strict=True),
            args.certificates.resolve(strict=True), output, sysroot, native, tools, run, inputs, report)
        crt_begin, crt_end = [crt / 'crtbeginS.o'], [crt / 'crtendS.o']
        # Linker lookup sees only this already verified closure.
        (payload / 'ld.so.1').symlink_to('ld_xos_x86_64.so.1')
        link = [ld, '--build-id=none', '--hash-style=both', '--no-undefined', '--eh-frame-hdr',
            '-z', 'noexecstack', '-z', 'now', '-z', 'relro', '-z', 'max-page-size=8192',
            '-z', 'separate-code', '-rpath-link', payload]
        compiler = cxx
        run('compile-main', [compiler, *extra, *flags, '-fPIE', '-fno-builtin', '-c', source, '-o', output / 'main.o'])
        main_image = payload / 'main.pie'
        run('link-main', [*link, '-pie', '-e', '_start', '--dynamic-linker', INTERPRETER, '-o', main_image,
            gnu / 'csu/Scrt1.o', gnu / 'csu/crti.o', *crt_begin, output / 'main_identity.o',
            output / 'main.o', *app_libraries, sysroot / 'usr/lib/libgcc.a', payload / 'libc.so.0.1',
            *crt_end, gnu / 'csu/crtn.o', '-Map', output / 'main.map'])
        report['compiler_support'] = {'artifact': 'usr/lib/libgcc.a',
            'sha256': digest(sysroot / 'usr/lib/libgcc.a'), 'link_map_sha256': digest(output / 'main.map'),
            'purpose': 'authenticated C SDK compiler arithmetic helpers; no second libc'}
        bootstrap = payload / 'bootstrap'
        run('compile-bootstrap', [cxx, *flags, '-nostdinc++', '-std=gnu++20', '-ffreestanding', '-fno-pie',
            '-fno-exceptions', '-fno-rtti', '-fno-stack-protector', '-I', output / 'native_headers',
            '-c', bootstrap_source, '-o', output / 'bootstrap.o'])
        linker = (sysroot / 'user.ld').read_text()
        if linker.count('    tls PT_TLS FLAGS(4);') != 1 or linker.count('    .xos.exec :') != 1:
            raise ValueError('native bootstrap linker script anchor changed')
        linker = linker.replace('    tls PT_TLS FLAGS(4);', '    tls PT_TLS FLAGS(4);\n    native PT_NOTE FLAGS(4);')
        linker = linker.replace('    .xos.exec :', '    .note.xos : { KEEP(*(.note.xos)) } :rodata :native\n'
            '    .xos.tty : { KEEP(*(.xos.tty)) } :rodata\n    .xos.exec :')
        (output / 'bootstrap.ld').write_text(linker)
        run('link-bootstrap', [ld, '--gc-sections', '-z', 'noexecstack', '-z', 'max-page-size=4096',
            '--build-id=none', '--no-undefined', '-T', output / 'bootstrap.ld', '-o', output / 'bootstrap.elf',
            sysroot / 'usr/lib/xos_start.o', output / 'bootstrap_identity.o', output / 'bootstrap.o',
            gnu / 'elf/xos_file_session.os', '--start-group', native / 'lib/libxos_loader.a',
            native / 'lib/libxos.a', sysroot / 'usr/lib/libgcc.a', '--end-group'])
        run('strip-bootstrap', [objcopy, '--strip-debug', output / 'bootstrap.elf', bootstrap])
        if bootstrap.stat().st_size > 131072:
            raise ValueError('native bootstrap exceeds ordinary static loader budget')
        entries = [(bootstrap, runtime_path + '/bootstrap'),
            (payload / 'ld_xos_x86_64.so.1', INTERPRETER),
            (main_image, '/usr/lib/xos/' + args.name + '/main'), *libraries]
        manifest, objects = generation_record(args.generation_id, args.sdk_manifest_sha256,
                                                metadata['native_abi'], entries)
        generation = payload / 'generation.bin'
        generation.write_bytes(manifest)
        preflight_sources = [repository_root / 'scripts/dynamic_preflight.cpp', repository_root / 'src/user/loader/elf.cpp',
            *(repository_root / 'src/user/loader/dynamic' / name for name in ('identity.cpp', 'generation.cpp', 'elf.cpp'))]
        for path in preflight_sources:
            inputs[str(path)] = digest(path)
        host = tool_identity('g++')
        report['host_compiler'] = host
        run('compile-preflight', [host['path'], '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror',
            '-Wconversion', '-Wshadow', '-I', repository_root / 'src/user/include', '-I', repository_root / 'src/shared/include',
            *preflight_sources, '-o', output / 'preflight'])
        run('preflight', [output / 'preflight', generation, *(local for local, _ in entries)])
        report['objects'] = [{k: v for k, v in item.items() if k not in ('identity', 'programs')} for item in objects]
        report['files'] = {guest: {'local': str(local.relative_to(output)), 'sha256': digest(local)}
                           for local, guest in entries}
        report['generation'] = {'local': str(generation.relative_to(output)),
            'guest': '/usr/lib/xos/generations/' + args.name + '.bin', 'id': args.generation_id,
            'sha256': digest(generation)}
        if (inspect_sdk('glibc', sdk)['binding'] != c_binding
                or inspect_native_sdk(original_native) != native_binding
                or inspect_native_sdk(native) != native_binding
                or any(digest(Path(name)) != expected for name, expected in inputs.items())):
            raise ValueError('a pinned build input changed')
        report['status'] = 'built_not_run'
        save()
    except BaseException as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        save()
        raise


if __name__ == '__main__':
    main()
