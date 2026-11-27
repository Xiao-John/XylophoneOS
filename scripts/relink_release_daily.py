#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Collect and replay the static links used by the released daily utilities XPK."""

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
from tempfile import TemporaryDirectory

from glibc_g1_probe import clean_build_environment
from relink_release_xypm import LIBC, LINK_FLAGS
from stage_glibc_daily_runtime import loaded_image
from xos_app import sdk_notices
from xypm_format import canonical, confined, inspect_elf, load_json, require, sha_file, strict_json, verify_package
from xypm_sdk_profile import require_stdio_marker

ROOT = Path(__file__).resolve().parents[1]
FORMAT = 'xos_release_daily_relink_v1'
COMPONENT = 'xos.daily_utilities'
PROGRAM_OBJECT = {'object': 'program_0.o'}
BUILD_TOOLS = ('gcc', 'as', 'ld', 'objcopy')
HELPERS = ('relink_release_daily.py', 'relink_release_xypm.py', 'glibc_g1_probe.py', 'glibc_g1_deps.py',
           'xypm_format.py', 'xypm_sdk_profile.py', 'xos_app.py', 'archive_member_map.py', 'verify_glibc_source.py',
           'stage_glibc_daily_runtime.py')


def package_files(archive, profile, digest):
    bodies = {}

    def capture(event, item, data):
        name = item['path']
        if name.startswith('usr/share/' + COMPONENT + '/') and item['role'] != 'executable':
            if event == 'begin':
                bodies[name] = bytearray()
            elif event == 'data':
                require(len(bodies[name]) + len(data) <= 1 << 20, 'unexpectedly large daily notice or receipt')
                bodies[name].extend(data)

    package = verify_package(archive, profile, expected_sha256=digest, sink=capture)['manifest']
    require(package['id'] == COMPONENT, 'unexpected daily package')
    receipt_path = package['build_receipt']['path']
    receipt = bytes(bodies.pop(receipt_path))
    require(hashlib.sha256(receipt).hexdigest() == package['build_receipt']['sha256'],
            'daily XPK receipt differs')
    executable = {item['path']: (item['sha256'], item['size']) for item in package['files']
                  if item['role'] == 'executable'}
    require(executable, 'daily XPK has no executables')
    return receipt, executable, bodies


def link_inputs(receipt, name, sysroot, artifacts, work):
    command, = (step['command'] for step in receipt['steps'] if step['name'] == 'link' and step['exit_code'] == 0)
    require(command[0] == receipt['compiler']['path'] and command[1].startswith('--sysroot=')
            and command[2].startswith('-B') and command.count('-o') == 1, 'unexpected link driver: ' + name)
    recorded_sdk = PurePosixPath(command[1].removeprefix('--sysroot='))
    index = command.index('-o')
    output = PurePosixPath(command[index + 1])
    require(recorded_sdk.is_absolute() and output.is_absolute() and output.name == 'program.elf'
            and output.parent.name == name + '.build'
            and PurePosixPath(command[2].removeprefix('-B')) == output.parent / 'tools',
            'unexpected recorded SDK or build location: ' + name)
    plan, sources = [], {}
    for word in command[3:index] + command[index + 2:]:
        if word in LINK_FLAGS:
            plan.append(word)
            continue
        path = PurePosixPath(word)
        if path == output.parent / 'program_0.o':
            plan.append(PROGRAM_OBJECT)
        else:
            require(path.suffix in ('.ld', '.o', '.a') and path.is_relative_to(recorded_sdk),
                    'unexpected link input: ' + word)
            relative = path.relative_to(recorded_sdk).as_posix()
            source = confined(sysroot, relative)
            require(sha_file(source) == artifacts[relative], 'SDK link input differs: ' + relative)
            key = 'sysroot/' + relative
            sources[key] = source
            plan.append({'file': key})
    require(plan.count(PROGRAM_OBJECT) == 1 and LIBC in sources, 'incomplete daily link: ' + name)
    sources['objects/' + name + '.o'] = confined(work, 'program_0.o')
    return plan, sources


def capture_release(args):
    release_path = confined(args.release, 'release_manifest.json')
    require(sha_file(release_path) == args.sha256, 'release manifest differs')
    release = load_json(release_path)
    require(sha_file(confined(args.candidate, 'candidate_manifest.json')) == release['candidate_manifest_sha256'],
            'candidate build differs from release')
    kit = args.release / 'application-sdk'
    sdk = kit / 'sdk'
    meta_path = sdk / 'manifest.json'
    profile_path = kit / 'profile.json'
    profile = load_json(profile_path)
    binding = release['application_sdk']
    require(sha_file(profile_path) == binding['profile_file_sha256']
            and sha_file(meta_path) == binding['sdk_manifest_sha256'], 'daily SDK binding differs')
    meta = load_json(meta_path)
    package = confined(args.release, 'packages/daily.xpk')
    runtime_bytes, executables, notices = package_files(package, profile, release['daily_sha256'])
    runtime = strict_json(runtime_bytes)
    stock = args.candidate / 'stock'
    full_path = confined(stock, 'tools/manifest.json')
    exact_runtime = confined(stock, 'runtime/manifest.json')
    require(runtime_bytes == exact_runtime.read_bytes()
            and sha_file(full_path) == runtime['debug_stage']['original_manifest_sha256']
            and runtime['debug_stage']['mode'] == 'strip-debug'
            and sha_file(ROOT / 'scripts/stage_glibc_daily_runtime.py') == runtime['debug_stage']['builder_sha256'],
            'daily debug or runtime staging receipt differs')
    for key in ('sdk_manifest_sha256', 'sdk_tree_sha256', 'profile_sha256'):
        require(runtime[key] == binding[key], 'daily receipt is bound to a different SDK')
    full = {item['name']: item for item in load_json(full_path)['tools']}
    shipped = {item['name']: item for item in runtime['tools']}
    require(len(full) == len(shipped) == len(runtime['tools']) == len(executables)
            and set(full) == set(shipped)
            and executables == {item['guest_path'][1:]: (item['elf_sha256'], item['size'])
                                for item in shipped.values()}, 'daily release executable set differs')

    tools = {name: meta['tools']['x86_64-elf-' + name]['sha256'] for name in BUILD_TOOLS}
    require(tools['gcc'] == runtime['compiler']['sha256']
            and tools['objcopy'] == runtime['debug_stage']['objcopy_sha256'], 'daily build tools differ')
    sources = {'receipt/release_manifest.json': release_path, 'receipt/full.json': full_path,
               'receipt/daily.json': exact_runtime, 'receipt/sdk_manifest.json': meta_path,
               'receipt/profile.json': profile_path}
    programs = {}
    plan = None
    for name, item in shipped.items():
        require(name.isascii() and name.isalpha() and item['guest_path'] == '/usr/bin/' + name,
                'unexpected daily tool identity')
        work = stock / 'tools' / (name + '.build')
        backend_path = confined(work, 'manifest.json')
        backend = load_json(backend_path)
        debug = confined(stock, 'tools/' + name)
        elf = confined(stock, 'runtime/' + name)
        require(sha_file(debug) == item['debug_sha256'] == full[name]['elf_sha256'] == backend['elf_sha256']
                and sha_file(elf) == item['elf_sha256'] and elf.stat().st_size == item['size'],
                'daily production ELF differs: ' + name)
        require(backend['status'] == 'static_program_linked' and backend['language'] == 'c'
                and backend['builder_sha256'] == sha_file(ROOT / 'scripts/build_glibc_program.py')
                and backend['sdk_manifest_sha256'] == binding['sdk_manifest_sha256']
                and backend['profile_binding']['profile_sha256'] == binding['profile_sha256']
                and list(backend['sources'].values()) == [item['source_sha256']]
                and backend['stdio_receiver_sha256'] == runtime['stdio_receiver_sha256']
                and backend['compiler']['sha256'] == tools['gcc']
                and {key: value['sha256'] for key, value in backend['binutils'].items()}
                == {key: tools[key] for key in ('as', 'ld')}, 'daily backend receipt differs: ' + name)
        current, inputs = link_inputs(backend, name, sdk / 'sysroot', meta['artifacts'], work)
        require(plan is None or plan == current, 'daily programs have different link recipes')
        plan = current
        sources.update(inputs)
        sources['receipt/backend/' + name + '.json'] = backend_path
        programs[name] = {key: item[key] for key in ('debug_sha256', 'elf_sha256', 'size')}

    sources.update({'licenses/sdk/' + name: file for file, name in sdk_notices(sdk, profile, 'c')})
    sources.update({'tools/' + name: ROOT / 'scripts' / name for name in HELPERS})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    require(not args.output.exists() and not args.output.is_symlink(), 'choose new materials output')
    with TemporaryDirectory(dir=args.output.parent) as directory:
        stage = Path(directory) / 'materials'
        for name, source in sources.items():
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        for name, data in notices.items():
            target = stage / 'licenses/package' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        files = {item.relative_to(stage).as_posix(): sha_file(item) for item in sorted(stage.rglob('*')) if item.is_file()}
        manifest = {'format': FORMAT, 'tools': tools, 'plan': plan, 'programs': programs,
                    'files': files, 'daily_xpk_sha256': release['daily_sha256']}
        (stage / 'manifest.json').write_bytes(canonical(manifest))
        stage.rename(args.output)
    print(sha_file(args.output / 'manifest.json'))


def relink(args):
    manifest_path = confined(args.materials, 'manifest.json')
    require(sha_file(manifest_path) == args.sha256, 'materials manifest differs')
    manifest = load_json(manifest_path)
    require(manifest['format'] == FORMAT and set(manifest['tools']) == set(BUILD_TOOLS),
            'unexpected daily materials')
    files = {name: confined(args.materials, name) for name in manifest['files']}
    require(all(sha_file(path) == manifest['files'][name] for name, path in files.items()), 'daily materials changed')
    tools = {}
    for name, digest in manifest['tools'].items():
        path = shutil.which('x86_64-elf-' + name)
        require(path is not None and sha_file(path) == digest, 'daily build tool differs: ' + name)
        tools[name] = Path(path).resolve(strict=True)
    if args.libc is not None:
        with args.libc.open('rb') as stream:
            require(stream.read(8) == b'!<arch>\n', 'expected a standalone replacement archive')
        require(sha_file(args.libc) == args.libc_sha256, 'replacement archive digest differs')
        files[LIBC] = args.libc.resolve(strict=True)
    output = args.output.resolve()
    require(not output.exists() and not args.output.is_symlink() and not output.is_relative_to(args.materials.resolve()),
            'choose new output outside the materials')
    output.parent.mkdir(parents=True, exist_ok=True)
    env, _ = clean_build_environment(os.environ)
    sums = {}
    with TemporaryDirectory(dir=output.parent) as directory:
        work = Path(directory)
        for name in ('as', 'ld'):
            (work / name).symlink_to(tools[name])
        debug = work / 'debug.elf'
        stage = work / 'result'
        stage.mkdir()
        for name, item in manifest['programs'].items():
            require(name.isascii() and name.isalpha(), 'unexpected daily tool name')
            flags = []
            for word in manifest['plan']:
                if word == PROGRAM_OBJECT:
                    flags.append(str(files['objects/' + name + '.o']))
                elif isinstance(word, str):
                    require(word in LINK_FLAGS, 'unexpected daily link flag')
                    flags.append(word)
                else:
                    require(word['file'].startswith('sysroot/'), 'unexpected daily link file')
                    flags.append(str(files[word['file']]))
            driver = [tools['gcc'], '--sysroot=' + str(args.materials.resolve() / 'sysroot'), '-B' + directory + '/']
            subprocess.run([*driver, '-o', debug, *flags], check=True, env=env)
            executable = stage / name
            subprocess.run([tools['objcopy'], '--strip-debug', debug, executable], check=True, env=env)
            require(inspect_elf(debug) == inspect_elf(executable)
                    and loaded_image(debug.read_bytes()) == loaded_image(executable.read_bytes()),
                    'debug stripping changed the loaded image: ' + name)
            require_stdio_marker(executable.read_bytes(), name)
            digest = sha_file(executable)
            if args.libc is None:
                require(sha_file(debug) == item['debug_sha256'] and digest == item['elf_sha256']
                        and executable.stat().st_size == item['size'], 'daily relink differs from release: ' + name)
            else:
                require(digest != item['elf_sha256'], 'replacement runtime did not change daily binary: ' + name)
            sums[name] = digest
        stage.rename(output)
    print(canonical(sums).decode(), end='')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    collect = actions.add_parser('collect')
    receive = actions.add_parser('relink')
    for action, paths in ((collect, ('release', 'candidate')), (receive, ('materials',))):
        for name in (*paths, 'output'):
            action.add_argument('--' + name, type=Path, required=True)
        action.add_argument('--sha256', required=True)
    receive.add_argument('--libc', type=Path)
    receive.add_argument('--libc-sha256')
    args = parser.parse_args()
    if args.action == 'collect':
        capture_release(args)
    else:
        if (args.libc is None) != (args.libc_sha256 is None):
            parser.error('--libc and --libc-sha256 must be supplied together')
        relink(args)


if __name__ == '__main__':
    main()
