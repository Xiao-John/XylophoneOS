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
GLIBC_BUILDER = ROOT / 'scripts/build_glibc_program.py'


def tree_receipt(root):
    root = Path(root).resolve(strict=True)
    result = {}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        require(not path.is_symlink(), 'SDK symlinks unsupported: ' + str(path))
        # Local Python/host-tool caches are not SDK inputs.  Importing tools or
        # running xypm must not invalidate the profile that binds this tree.
        if '__pycache__' in relative.parts or relative.suffix == '.pyc' or relative.parts[0] == '.cache':
            continue
        if path.is_file():
            result[relative.as_posix()] = sha_file(path)
    return hashlib.sha256(canonical(result)).hexdigest(), result


def sdk_check(sdk, profile):
    require(profile.get('runtime_family', 'newlib') == 'newlib',
            'this application builder requires the newlib runtime family; '
            'validate glibc candidates with create_xypm_profile.py')
    sdk = Path(sdk).resolve(strict=True)
    metadata = load_json(sdk / 'manifest.json')
    require(metadata.get('abi') == 1 and metadata.get('target') == 'x86_64-elf', 'unsupported SDK ABI/target')
    digest, files = tree_receipt(sdk)
    require(digest in profile['sdk_tree_sha256'], 'SDK snapshot not registered for profile; do not mix headers/libraries')
    required = ['crt0_posix.o', 'user.ld', 'lib/libxos.a', 'lib/libc.a', 'lib/libm.a']
    if profile.get('runtime_model', 'single') == 'single':
        required.append('lib/libxos_loader.a')
    if 'cxx_runtime' in profile.get('features', ()):
        required.append('cpp/lib/libgcc.a')
    for name in required:
        require(name in files, 'SDK missing ' + name)
    return {'tree_sha256': digest, 'files': files, 'sdk_build_id': metadata['build_id']}


def application_sdk_check(sdk, profile):
    if profile.get('runtime_family') != 'glibc':
        return sdk_check(sdk, profile)
    from xypm_sdk_profile import verify_profile

    binding = verify_profile(profile, 'glibc', sdk)
    return {'tree_sha256': binding['sdk_tree_sha256'],
            'sdk_manifest_sha256': profile['sdk_binding']['sdk_manifest_sha256']}


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


def build_glibc(project, value, sdk, profile, bound, inputs, output):
    with tempfile.TemporaryDirectory(prefix='glibc_app_', dir=output.parent) as folder:
        work = Path(folder)
        source_root = work / 'project'
        for name, expected in inputs.items():
            staged = source_root / name
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(confined(project, name), staged)
            require(sha_file(staged) == expected, 'project inputs changed while creating the build snapshot')
        profile_path = work / 'profile.json'
        profile_path.write_bytes(canonical(profile))
        inputs_path = work / 'inputs.json'
        inputs_path.write_bytes(canonical(inputs))
        linked = work / 'application.elf'
        cmd = [sys.executable, str(GLIBC_BUILDER), '--sdk', str(sdk / 'sysroot'),
               '--profile', str(profile_path), '--project-inputs', str(inputs_path), '--output', str(linked)]
        if (source_root / 'src').is_dir():
            cmd += ['--include-dir', str(source_root / 'src')]
        if value['language'] == 'cpp':
            cmd.append('--cxx')
        for source in value['sources']:
            cmd += ['--source', str(source_root / source)]
        result = subprocess.run(cmd, cwd=source_root)
        build_dir = work / 'application.elf.build'
        if result.returncode:
            for step in sorted(build_dir.glob('*.log')):
                diagnostics = step.read_text(errors='replace')
                if diagnostics:
                    print(diagnostics, file=sys.stderr, end='')
            require(False, 'glibc application build failed')
        backend = load_json(build_dir / 'manifest.json')
        profile_sha = hashlib.sha256(canonical(profile)).hexdigest()
        require(backend['status'] == 'static_program_linked'
                and backend['profile_binding']['profile_sha256'] == profile_sha
                and backend['sdk_manifest_sha256'] == bound['sdk_manifest_sha256']
                and backend['elf_sha256'] == sha_file(linked), 'glibc build output differs from its receipt')
        receipt = {'format_version': 1, 'builder_sha256': sha_file(__file__),
                   'backend_sha256': backend['builder_sha256'], 'runtime_family': 'glibc',
                   'project_id': value['id'], 'target_profile': profile['id'],
                   'profile_sha256': profile_sha, 'sdk_tree_sha256': bound['tree_sha256'],
                   'sdk_manifest_sha256': bound['sdk_manifest_sha256'],
                   'compiler': {name: backend['compiler'][name] for name in ('version', 'sha256')},
                   'binutils': {name: tool['sha256'] for name, tool in backend['binutils'].items()},
                   'inputs': inputs, 'output': output.relative_to(project).as_posix(),
                   'output_sha256': backend['elf_sha256'], 'elf_check': inspect_elf(linked),
                   'status': 'cross_built_guest_not_run'}
        require(inputs == input_receipt(project, value), 'project inputs changed during build')
        require(application_sdk_check(sdk, profile) == bound, 'SDK changed during build')
        require(receipt['backend_sha256'] == sha_file(GLIBC_BUILDER), 'glibc builder changed during build')
        staged_receipt = work / 'build_receipt.json'
        staged_receipt.write_bytes(canonical(receipt))
        os.replace(linked, output)
        os.replace(staged_receipt, output.parent / 'build_receipt.json')
    return receipt


def build(project, sdk, profile):
    project, value = project_load(project)
    require(value['target_profile'] == profile['id'],
            'project target_profile mismatch: project has %r, profile is %r; '
            'set target_profile in xos_app.json to the profile id, or re-init with '
            '--profile <adopted.json> from tools/adopt_sdk.py' %
            (value['target_profile'], profile['id']))
    require(set(value['required_features']) <= set(profile['features']), 'required feature unavailable')
    bound = application_sdk_check(sdk, profile)
    sdk = Path(sdk).resolve(strict=True)
    inputs = input_receipt(project, value)
    if profile.get('runtime_family') == 'glibc':
        return build_glibc(project, value, sdk, profile, bound, inputs, output_for(project, value))
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
           '-ftls-model=local-exec', '-idirafter', str(sdk / 'include'), '-I', str(project / 'src'),
           # The ordinary SDK ships a single-thread pthread subset; these POSIX
           # feature macros make its declarations visible to user programs.
           '-D_POSIX_THREADS=1', '-D_POSIX_READER_WRITER_LOCKS=200809L',
           '-D_UNIX98_THREAD_MUTEX_ATTRIBUTES=1']
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
    bound = application_sdk_check(sdk, profile)
    receipt = load_json(confined(project, 'build/build_receipt.json'))
    require(receipt['builder_sha256'] == sha_file(__file__), 'builder changed; rebuild before packing')
    require(receipt['project_id'] == value['id'] and receipt['target_profile'] == value['target_profile'] == profile['id'], 'receipt identity/profile mismatch')
    require(receipt['sdk_tree_sha256'] == bound['tree_sha256'] and receipt['profile_sha256'] == hashlib.sha256(canonical(profile)).hexdigest(), 'receipt SDK/profile mismatch')
    if profile.get('runtime_family') == 'glibc':
        require(receipt.get('runtime_family') == 'glibc'
                and receipt.get('sdk_manifest_sha256') == bound['sdk_manifest_sha256']
                and receipt.get('backend_sha256') == sha_file(GLIBC_BUILDER),
                'glibc build receipt SDK or backend mismatch')
    require(receipt['inputs'] == input_receipt(project, value), 'project inputs changed; rebuild before packing')
    output = output_for(project, value)
    require(receipt['output'] == output.relative_to(project).as_posix() and sha_file(output) == receipt['output_sha256'], 'executable differs from build receipt')
    inspect_elf(output)
    return project, value, receipt


def sdk_notices(sdk, profile, language):
    if profile.get('runtime_family') == 'glibc':
        root = sdk / 'sysroot'
        share = 'usr/share/xos-glibc/'
        required = [share + name for name in ('COPYING.LIB', 'LICENSES')]
        if language == 'cpp':
            required.extend(share + 'cxx/licenses/' + name for name in ('COPYING3', 'COPYING.RUNTIME'))
        for name in required:
            yield confined(root, name), name
        for directory in (share + 'compiler-runtime-licenses', 'usr/share/xos/terminal-support/licenses'):
            for source in sorted((root / directory).rglob('*')):
                if source.is_file():
                    name = source.relative_to(root).as_posix()
                    yield confined(root, name), name
        terminal_license = 'usr/share/xos/terminal-support/LICENSE'
        if (root / terminal_license).is_file():
            yield confined(root, terminal_license), terminal_license
        return
    for name in ('LICENSE', 'NOTICE', 'COPYING.NEWLIB'):
        yield confined(sdk, name), name
    for source in sorted((sdk / 'licenses').rglob('*')):
        if source.is_file():
            require(not source.is_symlink(), 'SDK notice symlink')
            yield source, source.relative_to(sdk).as_posix()


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
            expected = receipt['output_sha256'] if item['role'] == 'executable' else receipt['inputs'][item['source']]
            require(entries[-1]['sha256'] == expected, 'project payload changed during staging')
        receipt_dest = 'usr/share/' + value['id'] + '/build_receipt.json'
        original_receipt = stage / 'build_receipt.json'
        original_receipt.write_bytes(canonical(receipt))
        stage_file(original_receipt, receipt_dest, 'data')
        original_receipt.unlink()
        manifest['build_receipt'] = {'path': receipt_dest, 'sha256': sha_file(stage / receipt_dest)}
        for source, name in sdk_notices(sdk, profile, value['language']):
            dest = 'usr/share/licenses/' + value['id'] + '/sdk/' + name
            stage_file(source, dest, 'data'); manifest['licenses'].append(dest)
        manifest['files'] = sorted(entries, key=lambda x: x['path'])
        validate_manifest(manifest); check_profile(manifest, profile)
        # Recheck source/SDK snapshots after staging to avoid binding a mixed build.
        require(check(project, sdk, profile)[1:] == (value, receipt), 'project build changed during staging')
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
        command.add_argument('--sdk', type=Path, required=True,
                             help='newlib SDK directory or glibc SDK build directory for the selected profile')
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
