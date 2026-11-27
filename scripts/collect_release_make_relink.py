#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Collect the exact static link of GNU Make from a frozen release build and disk."""

import argparse
from pathlib import Path, PurePosixPath
import shlex
import shutil
from tempfile import TemporaryDirectory

from relink_release_xypm import LIBC, LINK_FLAGS, MAKE_FORMAT
from xos_app import sdk_notices
from xypm_format import canonical, confined, load_json, require, sha_file
from xypm_image import Disk
from xypm_sdk_profile import require_stdio_marker

ROOT = Path(__file__).resolve().parents[1]
MAKE_PATH = '/usr/bin/gmake'
LINK_START = ['-nostdlib', '-static', '-no-pie',
              '-Wl,--gc-sections,--build-id=none,-z,noexecstack,-z,max-page-size=4096']


def link_inputs(build, receipt, sdk, sdk_artifacts):
    log = confined(build, 'compile.log')
    step, = (item for item in receipt['steps'] if item['step'] == 'compile')
    require(step['returncode'] == 0 and sha_file(log) == step['log_sha256'], 'compile log differs from the receipt')
    gcc = receipt['tools']['gcc']['path']
    command, = (shlex.split(line) for line in log.read_text().splitlines()
                if line.startswith(gcc + ' ') and ' -o make ' in line)
    require(command[1].startswith('--sysroot=') and command[2].startswith('-B') and command.count('-o') == 1,
            'unexpected GNU Make link driver')
    sysroot = PurePosixPath(command[1].removeprefix('--sysroot='))
    out = command.index('-o')
    require(sysroot.is_absolute() and
            command[out - len(LINK_START):out + 2] == [*LINK_START, '-o', 'make'],
            'unexpected GNU Make final link flags')
    plan = list(LINK_START)
    sources = {}
    for option in command[out + 2:]:
        if option in LINK_FLAGS:
            plan.append(option)
            continue
        path = PurePosixPath(option)
        if path.is_relative_to(sysroot):
            relative = path.relative_to(sysroot).as_posix()
            incoming = confined(sdk / 'sysroot', relative)
            require(path.suffix in ('.a', '.o', '.ld') and sha_file(incoming) == sdk_artifacts[relative],
                    'SDK link input differs: ' + relative)
            name = 'sysroot/' + relative
        else:
            require((path.parent.as_posix() == 'src' and path.suffix == '.o')
                    or option == 'lib/libgnu.a', 'unexpected non-SDK link input')
            incoming = confined(build, 'target/' + option)
            name = 'objects/' + option
        require(name not in sources, 'duplicate link input: ' + name)
        sources[name] = incoming
        plan.append({'file': name})
    require(LIBC in sources and 'objects/src/main.o' in sources and 'objects/lib/libgnu.a' in sources,
            'incomplete GNU Make link')
    sources['receipt/compile.log'] = log
    return plan, sources


def collect(args):
    release_path = confined(args.release, 'release_manifest.json')
    require(sha_file(release_path) == args.sha256, 'release manifest differs')
    release = load_json(release_path)
    seed_path = confined(args.release, 'images/gnu_seed_receipt.json')
    require(sha_file(seed_path) == release['gnu_seed']['receipt']['sha256'], 'GNU Seed receipt differs')
    seed = load_json(seed_path)
    binary_sha = seed['installed_files'][MAKE_PATH]
    build_receipt = confined(args.build, 'manifest.json')
    require(sha_file(build_receipt) == seed['make_receipt_sha256'], 'GNU Make production receipt differs')
    receipt = load_json(build_receipt)
    binary = confined(args.build, receipt['elf']['path'])
    require(receipt['version'] == '4.4.1' and receipt['target'] == 'x86_64-unknown-xos'
            and receipt['status'] == 'built_not_run' and sha_file(binary) == receipt['elf']['sha256'] == binary_sha,
            'GNU Make production ELF differs')
    require_stdio_marker(binary.read_bytes(), MAKE_PATH)

    disk = confined(args.release, 'images/work_disk.img')
    require(sha_file(disk) == seed['work_disk_sha256'] == release['work_disk']['sha256'], 'frozen work disk differs')
    with TemporaryDirectory() as folder, Disk(disk, Path(folder), read_only=True) as fat:
        require(sha_file(fat.export(MAKE_PATH)) == binary_sha, 'work disk GNU Make differs')

    kit = args.release / 'application-sdk'
    sdk = kit / 'sdk'
    sdk_manifest = confined(sdk, 'manifest.json')
    profile_path = confined(kit, 'profile.json')
    binding = release['application_sdk']
    require(sha_file(sdk_manifest) == receipt['sdk_manifest_sha256'] == binding['sdk_manifest_sha256']
            and sha_file(profile_path) == receipt['profile_sha256'] == binding['profile_file_sha256']
            and receipt['sdk_tree_sha256'] == binding['sdk_tree_sha256'], 'GNU Make uses another SDK')
    metadata = load_json(sdk_manifest)
    tools = {name: receipt['tools'][name]['sha256'] for name in ('gcc', 'as', 'ld')}
    require(all(metadata['tools']['x86_64-elf-' + name]['sha256'] == digest for name, digest in tools.items()),
            'GNU Make tools differ from SDK')
    plan, sources = link_inputs(args.build, receipt, sdk, metadata['artifacts'])

    config = confined(args.build, 'target/src/config.h')
    require(sha_file(config) == receipt['config_sha256'], 'configured header differs')
    sources.update({'receipt/gnu_make.json': build_receipt, 'receipt/gnu_seed_receipt.json': seed_path,
                    'receipt/release_manifest.json': release_path, 'receipt/sdk_manifest.json': sdk_manifest,
                    'receipt/profile.json': profile_path, 'receipt/config.h': config})
    for name, expected in receipt['inputs'].items():
        source = confined(ROOT, name)
        require(sha_file(source) == expected, 'GNU Make recipe or source lock differs: ' + name)
        sources['source/' + name] = source
    for source, name in sdk_notices(sdk, load_json(profile_path), 'c'):
        sources['licenses/' + name] = source
    for name in ('relink_release_xypm.py', 'glibc_g1_probe.py', 'glibc_g1_deps.py', 'xypm_format.py'):
        sources['tools/' + name] = ROOT / 'scripts' / name

    args.output.parent.mkdir(parents=True, exist_ok=True)
    require(not args.output.exists() and not args.output.is_symlink(), 'choose new materials output')
    with TemporaryDirectory(dir=args.output.parent) as folder:
        stage = Path(folder) / 'materials'
        files = {}
        for name, source in sorted(sources.items()):
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            files[name] = sha_file(target)
        manifest = {'format': MAKE_FORMAT, 'plan': plan, 'files': files, 'tools': tools,
                    'reference': binary_sha, 'work_disk_sha256': release['work_disk']['sha256']}
        (stage / 'manifest.json').write_bytes(canonical(manifest))
        stage.rename(args.output)
    print(sha_file(args.output / 'manifest.json'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('release', 'build', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--sha256', required=True)
    collect(parser.parse_args())


if __name__ == '__main__':
    main()
