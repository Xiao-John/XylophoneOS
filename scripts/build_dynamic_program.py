#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build a public native GNU program, bootstrap and approved-root candidate generation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from dynamic_artifacts import INTERPRETER, digest, generation_record, write_note
from glibc_g1_probe import clean_build_environment, tool_identity
from xypm_sdk_profile import inspect_sdk, relative_file, metadata_snapshot, sdk_snapshot

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = '/usr/lib/xos/glibc_dynamic_v1'


def inspect_native_sdk(path):
    metadata, manifest = metadata_snapshot(path / 'manifest.json')
    tree, _ = sdk_snapshot(path)
    if metadata.get('target') != 'x86_64-elf' or metadata.get('abi') != 1:
        raise ValueError('unexpected native SDK ABI')
    for name in ('user.ld', 'crt0.o', 'include/xos/dynamic_launch.hpp',
                 'lib/libxos.a', 'lib/libxos_loader.a'):
        relative_file(path, name)
    if digest(path / 'manifest.json') != manifest or sdk_snapshot(path)[0] != tree:
        raise ValueError('native SDK changed during full inventory')
    return {'sdk_manifest_sha256': manifest, 'sdk_tree_sha256': tree,
            'target': metadata['target'], 'abi': metadata['abi']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('sdk-build', 'native-sdk', 'runtime-build', 'source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('sdk-manifest-sha256', 'sdk-tree-sha256', 'native-sdk-manifest-sha256', 'native-sdk-tree-sha256'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--generation-id', type=int, required=True)
    parser.add_argument('--gcc-shared-build', type=Path)
    parser.add_argument('--unwinder-build', type=Path,
                        help='matched public unwinder-only build for C programs using native pthreads')
    parser.add_argument('--library-source', type=Path)
    parser.add_argument('--online-library-spec', type=Path,
                        help='ordered approved online C libraries; requires the explicit online runtime')
    parser.add_argument('--cxx', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', args.name):
        parser.error('name must be a bounded canonical native component')
    if args.cxx != bool(args.gcc_shared_build) or (args.library_source and not args.cxx):
        parser.error('C++ requires the matching public shared GCC build')
    if args.online_library_spec and (args.cxx or args.library_source):
        parser.error('the initial online-library builder accepts C libraries')
    if args.unwinder_build and args.gcc_shared_build:
        parser.error('select either the full GCC composition or the unwinder-only composition')
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
    if args.online_library_spec and not metadata.get('online_libraries'):
        raise ValueError('online libraries require the explicitly selected online runtime')
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
    tools = {name: tool_identity('x86_64-elf-' + name) for name in ('gcc', 'g++', 'ld', 'objcopy', 'readelf')}
    c_metadata = json.loads((sdk / 'manifest.json').read_bytes())
    for name, tool in tools.items():
        if tool.get('sha256') != c_metadata['tools']['x86_64-elf-' + name]['sha256']:
            raise ValueError('selected build tool differs from the anchored SDK')
    source = args.source.resolve(strict=True)
    inputs = {str(source): digest(source), str(runtime / 'manifest.json'): digest(runtime / 'manifest.json')}
    for path in sorted((source.parent).glob('*.h*')):
        inputs[str(path)] = digest(path)
    bootstrap_source = ROOT / 'src/user/loader/dynamic/bootstrap.cpp'
    for path in (bootstrap_source, ROOT / 'src/user/loader/dynamic/startup.hpp',
                 Path(__file__), ROOT / 'scripts/dynamic_artifacts.py', ROOT / 'scripts/dynamic_preflight.cpp'):
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
        libraries = [(payload / 'libc.so.0.1', RUNTIME_PATH + '/libc.so.0.1')]
        extra, app_libraries, crt_begin, crt_end = [], [], [], []
        if args.unwinder_build:
            unwinder = args.unwinder_build.resolve(strict=True)
            path = unwinder / 'manifest.json'
            data = json.loads(path.read_bytes())
            if (data.get('status') != 'built_not_run' or data.get('scope') != 'public_native_unwinder_only'
                    or not data.get('public_startup') or data['native_abi'] != metadata['native_abi']
                    or data['public_runtime_manifest_sha256'] != digest(runtime / 'manifest.json')
                    or data['sdk_manifest_sha256'] != args.sdk_manifest_sha256
                    or data['sdk_tree_sha256'] != args.sdk_tree_sha256
                    or data['libc_sha256'] != digest(gnu / 'libc.so')
                    or data['interpreter_sha256'] != digest(gnu / 'elf/ld.so')):
                raise ValueError('the unwinder belongs to another native composition')
            original = relative_file(unwinder, 'lib/libgcc_s.so.1')
            if digest(original) != data['artifacts']['libgcc_s.so.1']:
                raise ValueError('the bound unwinder bytes changed')
            inputs[str(path)] = digest(path)
            inputs[str(original)] = digest(original)
            run('strip-unwinder', [objcopy, '--strip-debug', original, payload / 'libgcc_s.so.1'])
            libraries.append((payload / 'libgcc_s.so.1', RUNTIME_PATH + '/libgcc_s.so.1'))
            app_libraries.append(payload / 'libgcc_s.so.1')
        if args.cxx:
            shared = args.gcc_shared_build.resolve(strict=True)
            shared_metadata = json.loads((shared / 'manifest.json').read_bytes())
            if (not shared_metadata.get('public_startup') or shared_metadata['native_abi'] != metadata['native_abi']
                    or shared_metadata['libc_sha256'] != digest(gnu / 'libc.so')
                    or shared_metadata['interpreter_sha256'] != digest(gnu / 'elf/ld.so')
                    or shared_metadata['public_runtime_manifest_sha256'] != digest(runtime / 'manifest.json')):
                raise ValueError('GCC DSOs belong to another native composition')
            inputs[str(shared / 'manifest.json')] = digest(shared / 'manifest.json')
            for name, expected in shared_metadata['headers'].items():
                if digest(relative_file(shared, name)) != expected:
                    raise ValueError('shared GCC header changed: ' + name)
            extra = ['-nostdinc++', '-std=gnu++20']
            for name in shared_metadata['include_directories']:
                extra += ['-isystem', shared / name]
            for name in ('libgcc_s.so.1', 'libm.so.0.1', 'libstdc++.so.6'):
                original = relative_file(shared, 'lib/' + name)
                if digest(original) != shared_metadata['artifacts'][name]:
                    raise ValueError('shared GCC object changed: ' + name)
                run('strip-' + name, [objcopy, '--strip-debug', original, payload / name])
                libraries.append((payload / name, RUNTIME_PATH + '/' + name))
            app_libraries = [shared / 'lib/atexit.oS', payload / 'libstdc++.so.6', payload / 'libgcc_s.so.1']
            crt_begin, crt_end = [crt / 'crtbeginS.o'], [crt / 'crtendS.o']
        # Linker lookup sees only this already verified closure.
        (payload / 'ld.so.1').symlink_to('ld_xos_x86_64.so.1')
        link = [ld, '--build-id=none', '--hash-style=both', '--no-undefined', '--eh-frame-hdr',
            '-z', 'noexecstack', '-z', 'now', '-z', 'relro', '-z', 'max-page-size=8192',
            '-z', 'separate-code', '-rpath-link', payload]
        if args.library_source:
            module_source = args.library_source.resolve(strict=True)
            inputs[str(module_source)] = digest(module_source)
            for path in module_source.parent.glob('*.h*'):
                inputs[str(path)] = digest(path)
            # libstdc++ uses include_next for C headers; its include roots must
            # precede the selected libc include roots, including with nostdinc.
            run('compile-library', [cxx, *extra, *flags, '-I', module_source.parent, '-fPIC', '-c',
                module_source, '-o', output / 'library.o'])
            run('link-library', [*link, '-shared', '-soname', 'libsample.so', '-o', payload / 'libsample.so',
                gnu / 'csu/crti.o', *crt_begin, output / 'library_identity.o', output / 'library.o',
                payload / 'libstdc++.so.6', payload / 'libgcc_s.so.1', payload / 'libc.so.0.1',
                payload / 'ld.so.1', *crt_end, gnu / 'csu/crtn.o'])
            libraries.append((payload / 'libsample.so', '/apps/' + args.name + '/libsample.so'))
            app_libraries.insert(0, payload / 'libsample.so')
        online_sonames = []
        if args.online_library_spec:
            spec_path = args.online_library_spec.resolve(strict=True)
            spec = json.loads(spec_path.read_bytes())
            inputs[str(spec_path)] = digest(spec_path)
            if (set(spec) != {'version', 'libraries'} or spec['version'] != 1
                    or not isinstance(spec['libraries'], list) or not 1 <= len(spec['libraries']) <= 8):
                raise ValueError('invalid bounded online library specification')
            for item in spec['libraries']:
                if (not isinstance(item, dict)
                        or set(item) != {'soname', 'source', 'dependencies', 'with_libc'}
                        or not re.fullmatch(r'lib[a-z0-9_]+\.so', item['soname'])
                        or item['soname'] in online_sonames
                        or not isinstance(item['dependencies'], list)
                        or len(set(item['dependencies'])) != len(item['dependencies'])
                        or any(name not in online_sonames for name in item['dependencies'])
                        or type(item['with_libc']) is not bool):
                    raise ValueError('online dependencies must be distinct preceding approved libraries')
                module_source = (spec_path.parent / item['source']).resolve(strict=True)
                inputs[str(module_source)] = digest(module_source)
                for path in module_source.parent.glob('*.h*'):
                    inputs[str(path)] = digest(path)
                name = item['soname']
                obj = output / (name + '.o')
                run('compile-online-' + name, [cc, *flags, '-I', module_source.parent,
                    '-fPIC', '-ftls-model=global-dynamic', '-fno-builtin', '-c', module_source, '-o', obj])
                dependencies = [payload / dependency for dependency in item['dependencies']]
                # An isolated namespace has no second libc/rtld or thread runtime.
                # Self-contained DSOs still use real GNU init/fini arrays.
                support = ([payload / 'libc.so.0.1', payload / 'ld.so.1']
                           if item['with_libc'] else [])
                run('link-online-' + name, [*link, '-shared', '-soname', name,
                    '-o', payload / name, output / 'library_identity.o', obj,
                    *dependencies, *support])
                libraries.append((payload / name, '/apps/' + args.name + '/' + name))
                online_sonames.append(name)
            report['online_libraries'] = spec
        compiler = cxx if args.cxx else cc
        run('compile-main', [compiler, *extra, *flags, '-fPIE', '-fno-builtin', '-c', source, '-o', output / 'main.o'])
        main_image = payload / 'main.pie'
        run('link-main', [*link, '-pie', '-e', '_start', '--dynamic-linker', INTERPRETER, '-o', main_image,
            *(['--export-dynamic'] if args.online_library_spec else []),
            gnu / 'csu/Scrt1.o', gnu / 'csu/crti.o', *crt_begin, output / 'main_identity.o',
            output / 'main.o', *app_libraries, payload / 'libc.so.0.1', *crt_end, gnu / 'csu/crtn.o'])
        bootstrap = payload / 'bootstrap'
        run('compile-bootstrap', [cxx, *flags, '-nostdinc++', '-std=gnu++20', '-ffreestanding', '-fno-pie',
            '-fno-exceptions', '-fno-rtti', '-fno-stack-protector', '-I', native / 'include',
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
        entries = [(bootstrap, RUNTIME_PATH + '/bootstrap'),
            (payload / 'ld_xos_x86_64.so.1', INTERPRETER),
            (main_image, '/apps/' + args.name + '/main'), *libraries]
        manifest, objects = generation_record(args.generation_id, args.sdk_manifest_sha256,
                                                metadata['native_abi'], entries,
                                                online_sonames=online_sonames)
        generation = payload / 'generation.bin'
        generation.write_bytes(manifest)
        preflight_sources = [ROOT / 'scripts/dynamic_preflight.cpp', ROOT / 'src/user/loader/elf.cpp',
            *(ROOT / 'src/user/loader/dynamic' / name for name in ('identity.cpp', 'generation.cpp', 'elf.cpp'))]
        for path in preflight_sources:
            inputs[str(path)] = digest(path)
        host = tool_identity('g++')
        report['host_compiler'] = host
        run('compile-preflight', [host['path'], '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror',
            '-Wconversion', '-Wshadow', '-I', ROOT / 'src/user/include', '-I', ROOT / 'src/shared/include',
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
