# SPDX-License-Identifier: Apache-2.0
"""Build independent XOS applications and deterministic XPKs; no system rebuild."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from xypm_format import (DEFAULT_PROFILE, PackageError, canonical, check_profile, confined,
                         fields, identifier, inspect_elf, load_json, pack_package,
                         path_name, require, sha_file, text, validate_manifest)

ROOT = Path(__file__).resolve().parents[1]


def tree_receipt(root):
    root = Path(root).resolve(strict=True)
    result = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'SDK symlinks unsupported: ' + str(path))
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha_file(path)
    return hashlib.sha256(canonical(result)).hexdigest(), result


def sdk_check(sdk, profile):
    sdk = Path(sdk).resolve(strict=True)
    metadata = load_json(sdk / 'manifest.json')
    require(metadata.get('abi') == 1 and metadata.get('target') == 'x86_64-elf', 'unsupported SDK ABI/target')
    digest, files = tree_receipt(sdk)
    require(digest in profile['sdk_tree_sha256'], 'SDK snapshot not registered for profile; do not mix headers/libraries')
    for name in ('crt0_posix.o', 'user.ld', 'lib/libxos.a', 'lib/libxos_loader.a',
                 'lib/libc.a', 'lib/libm.a', 'cpp/lib/libgcc.a'):
        require(name in files, 'SDK missing ' + name)
    return {'tree_sha256': digest, 'files': files, 'sdk_build_id': metadata['build_id']}


def project_load(project):
    project = Path(project).resolve(strict=True)
    require(project.is_dir(), 'project must be a directory')
    value = load_json(confined(project, 'xos_app.json'))
    fields(value, ('format_version', 'id', 'upstream_version', 'revision', 'target_profile',
                   'language', 'sources', 'required_features', 'runtime_dependencies', 'files', 'licenses'))
    require(type(value['format_version']) is int and value['format_version'] == 1, 'unsupported application format')
    identifier(value['id']); identifier(value['target_profile'])
    text(value['upstream_version'], 'version')
    require(type(value['revision']) is int and 0 <= value['revision'] < (1 << 31), 'invalid revision')
    require(value['language'] in ('c', 'cpp'), 'language must be c or cpp')
    require(type(value['sources']) is list and 0 < len(value['sources']) <= 128, 'invalid source count')
    require(len(value['sources']) == len(set(value['sources'])), 'duplicate source')
    for source in value['sources']:
        confined(project, source)
        require(Path(source).suffix in (('.c',) if value['language'] == 'c' else ('.cpp', '.cc', '.cxx')), 'source language mismatch')
    require(type(value['files']) is list and 0 < len(value['files']) <= 8000, 'invalid project files')
    for item in value['files']:
        fields(item, ('source', 'path', 'role'))
        path_name(item['source'], managed=False); path_name(item['path'])
        require(item['role'] in ('data', 'executable'), 'invalid project payload role')
    require(type(value['licenses']) is list and value['licenses'], 'application license required')
    return project, value


def input_receipt(project, value):
    names = set(value['sources']) | {'xos_app.json'}
    names.update(item['source'] for item in value['files'] if item['role'] != 'executable')
    # Include local headers, even when not listed as translation units.
    for path in (project / 'src').rglob('*'):
        require(not path.is_symlink(), 'source symlink rejected')
        if path.is_file():
            names.add(path.relative_to(project).as_posix())
    return {name: sha_file(confined(project, name)) for name in sorted(names)}


def output_for(project, value):
    outputs = [x for x in value['files'] if x['role'] == 'executable']
    require(len(outputs) == 1, 'P0 builds one executable; use xypm pack for a pre-staged multi-program package')
    relative = outputs[0]['source']
    require(relative.startswith('build/') and len(relative.split('/')) == 2, 'executable output must be a direct build/ file')
    folder = project / 'build'
    require(not folder.is_symlink(), 'build directory cannot be a symlink')
    folder.mkdir(exist_ok=True)
    require(not (project / relative).is_symlink(), 'output symlink rejected')
    return project / relative


def build(project, sdk, profile):
    project, value = project_load(project)
    require(value['target_profile'] == profile['id'], 'project target profile mismatch')
    require(set(value['required_features']) <= set(profile['features']), 'required feature unavailable')
    sdk = Path(sdk).resolve(strict=True)
    bound = sdk_check(sdk, profile)
    inputs = input_receipt(project, value)
    compiler = os.environ.get('XOS_CC' if value['language'] == 'c' else 'XOS_CXX',
                              'x86_64-elf-gcc' if value['language'] == 'c' else 'x86_64-elf-g++')
    for variable in ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH', 'LIBRARY_PATH', 'COMPILER_PATH', 'GCC_EXEC_PREFIX'):
        require(not os.environ.get(variable), 'ambient compiler injection variable must be unset: ' + variable)
    resolved = shutil.which(compiler)
    require(resolved is not None, 'cross compiler not found: ' + compiler)
    machine = subprocess.check_output([resolved, '-dumpmachine'], text=True).strip()
    version = subprocess.check_output([resolved, '-dumpfullversion'], text=True).strip()
    require(machine == 'x86_64-elf' and version == profile['compiler_version'], 'compiler target/version mismatch')
    output = output_for(project, value)
    # Compile to a fresh file; failure cannot make an old executable look newly built.
    fd, temporary = tempfile.mkstemp(prefix='app_', suffix='.elf', dir=output.parent)
    os.close(fd)
    temporary = Path(temporary)
    cmd = [resolved, '-O2', '-mno-red-zone', '-fno-pie', '-fno-pic', '-fno-stack-protector',
           '-ftls-model=local-exec', '-idirafter', str(sdk / 'include'), '-I', str(project / 'src')]
    if value['language'] == 'cpp':
        cmd += ['-std=gnu++17', '-nostdinc++', '-fuse-cxa-atexit']
        for name in ('', '/x86_64-unknown-elf', '/backward'):
            cmd += ['-isystem', str(sdk / 'cpp/include/c++/16.2.0') + name]
    else:
        cmd += ['-std=c11']
    cmd += ['-nostdlib', '-static', '-no-pie', '-Wl,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
            '-T', str(sdk / 'user.ld'), str(sdk / 'crt0_posix.o')]
    cmd += [str(project / source) for source in value['sources']]
    cmd += ['-Wl,--start-group', str(sdk / 'lib/libxos.a'), str(sdk / 'lib/libxos_loader.a')]
    if value['language'] == 'cpp':
        cmd += [str(sdk / 'cpp/lib/libstdc++.a'), str(sdk / 'cpp/lib/libsupc++.a')]
    cmd += [str(sdk / 'lib/libc.a'), str(sdk / 'lib/libm.a'), str(sdk / 'cpp/lib/libgcc.a'),
            '-Wl,--end-group', '-o', str(temporary)]
    try:
        subprocess.run(cmd, cwd=project, check=True)
        layout = inspect_elf(temporary)
        require(inputs == input_receipt(project, value), 'project inputs changed during build')
        # Detect a concurrent SDK rebuild as well as initial snapshot mismatch.
        require(tree_receipt(sdk)[0] == bound['tree_sha256'], 'SDK changed during build')
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    receipt = {'format_version': 1, 'builder_sha256': sha_file(__file__), 'project_id': value['id'], 'target_profile': profile['id'],
               'profile_sha256': hashlib.sha256(canonical(profile)).hexdigest(),
               'sdk_tree_sha256': bound['tree_sha256'], 'sdk_build_id': bound['sdk_build_id'],
               'compile_command': [Path(resolved).name] + [arg.replace(str(temporary), '$OUTPUT').replace(str(sdk), '$SDK').replace(str(project), '$PROJECT') for arg in cmd[1:]],
               'compiler': {'name': Path(resolved).name, 'version': version, 'target': machine,
                            'sha256': sha_file(resolved)},
               'inputs': inputs, 'output': output.relative_to(project).as_posix(),
               'output_sha256': sha_file(output), 'elf_check': layout,
               'status': 'cross_built_guest_not_run'}
    (project / 'build/build_receipt.json').write_bytes(canonical(receipt))
    return receipt


def check(project, sdk, profile):
    project, value = project_load(project)
    bound = sdk_check(sdk, profile)
    receipt = load_json(confined(project, 'build/build_receipt.json'))
    require(receipt['builder_sha256'] == sha_file(__file__), 'builder changed; rebuild before packing')
    require(receipt['project_id'] == value['id'] and receipt['target_profile'] == value['target_profile'] == profile['id'], 'receipt identity/profile mismatch')
    require(receipt['sdk_tree_sha256'] == bound['tree_sha256'] and receipt['profile_sha256'] == hashlib.sha256(canonical(profile)).hexdigest(), 'receipt SDK/profile mismatch')
    require(receipt['inputs'] == input_receipt(project, value), 'project inputs changed; rebuild before packing')
    output = output_for(project, value)
    require(receipt['output'] == output.relative_to(project).as_posix() and sha_file(output) == receipt['output_sha256'], 'executable differs from build receipt')
    inspect_elf(output)
    return project, value, receipt


def pack(project, sdk, profile, output):
    project, value, receipt = check(project, sdk, profile)
    sdk = Path(sdk).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='xos_app_stage_') as folder:
        stage = Path(folder)
        manifest = {key: value[key] for key in ('format_version', 'id', 'upstream_version', 'revision',
                    'target_profile', 'required_features', 'runtime_dependencies', 'licenses')}
        manifest['licenses'] = list(manifest['licenses'])
        manifest['source'] = 'project inputs in embedded build receipt; application source supplied by publisher'
        entries = []
        def stage_file(source, destination, role):
            path_name(destination)
            dest = stage / destination
            require(not dest.exists(), 'duplicate staged path')
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            entries.append({'path': destination, 'type': 'file', 'size': dest.stat().st_size,
                            'sha256': sha_file(dest), 'role': role})
        for item in value['files']:
            stage_file(confined(project, item['source']), item['path'], item['role'])
        receipt_dest = 'usr/share/' + value['id'] + '/build_receipt.json'
        stage_file(confined(project, 'build/build_receipt.json'), receipt_dest, 'data')
        manifest['build_receipt'] = {'path': receipt_dest, 'sha256': sha_file(stage / receipt_dest)}
        # Carry actual frozen SDK notices, not an invented blanket runtime license.
        for name in ('LICENSE', 'NOTICE', 'COPYING.NEWLIB'):
            source = confined(sdk, name)
            dest = 'usr/share/licenses/' + value['id'] + '/sdk/' + name
            stage_file(source, dest, 'data'); manifest['licenses'].append(dest)
        for source in sorted((sdk / 'licenses').rglob('*')):
            if source.is_file():
                require(not source.is_symlink(), 'SDK notice symlink')
                dest = 'usr/share/licenses/' + value['id'] + '/sdk/licenses/' + source.relative_to(sdk / 'licenses').as_posix()
                stage_file(source, dest, 'data'); manifest['licenses'].append(dest)
        manifest['files'] = sorted(entries, key=lambda x: x['path'])
        validate_manifest(manifest); check_profile(manifest, profile)
        # Recheck source/SDK snapshots after staging to avoid binding a mixed build.
        check(project, sdk, profile)
        result = pack_package(stage, manifest, output)
        return {'package': str(output), 'sha256': result['sha256'], 'files': result['payload_files'],
                'target_profile': profile['id'], 'status': 'packed_guest_not_run'}


def init_project(destination, name, language, profile):
    identifier(name)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    try:
        (destination / 'src').mkdir()
        basename = name.rsplit('.', 1)[-1].replace('-', '_')
        source = 'src/main.' + ('c' if language == 'c' else 'cpp')
        body = ('#include <stdio.h>\nint main(void) { puts("Hello from XOS package: ' + name + '"); return 0; }\n'
                if language == 'c' else '#include <cstdio>\n#include <string>\nint main() { std::string message("Hello from XOS package: ' + name + '"); std::puts(message.c_str()); return 0; }\n')
        (destination / source).write_text('// SPDX-License-Identifier: Apache-2.0\n' + body)
        shutil.copyfile(ROOT / 'LICENSE', destination / 'LICENSE')
        value = {'format_version': 1, 'id': name, 'upstream_version': '0.1.0', 'revision': 0,
                 'target_profile': profile['id'], 'language': language, 'sources': [source],
                 'required_features': ['stdio'] + (['cxx_runtime'] if language == 'cpp' else []),
                 'runtime_dependencies': [], 'files': [
                     {'source': 'build/' + basename + '.elf', 'path': 'usr/bin/' + basename, 'role': 'executable'},
                     {'source': 'LICENSE', 'path': 'usr/share/licenses/' + name + '/LICENSE', 'role': 'data'},
                     {'source': source, 'path': 'usr/share/' + name + '/source/main.' + ('c' if language == 'c' else 'cpp'), 'role': 'data'}],
                 'licenses': ['usr/share/licenses/' + name + '/LICENSE']}
        (destination / 'xos_app.json').write_bytes(canonical(value))
        (destination / '.gitignore').write_text('build/\ndist/\n')
    except BaseException:
        shutil.rmtree(destination)
        raise
    return {'project': str(destination), 'id': name, 'status': 'initialized'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, default=DEFAULT_PROFILE)
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init'); init.add_argument('project', type=Path)
    init.add_argument('--id', required=True); init.add_argument('--language', choices=('c', 'cpp'), default='c')
    for name in ('build', 'check', 'pack'):
        command = sub.add_parser(name); command.add_argument('project', type=Path)
        command.add_argument('--sdk', type=Path, required=True)
        if name == 'pack':
            command.add_argument('-o', '--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        profile = load_json(args.profile)
        if args.command == 'init':
            result = init_project(args.project, args.id, args.language, profile)
        elif args.command == 'build':
            result = build(args.project, args.sdk, profile)
        elif args.command == 'check':
            _, value, receipt = check(args.project, args.sdk, profile)
            result = {'id': value['id'], 'elf': receipt['output'], 'status': 'checked_guest_not_run'}
        else:
            result = pack(args.project, args.sdk, profile, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print('xos_app: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
