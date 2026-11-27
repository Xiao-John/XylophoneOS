# SPDX-License-Identifier: Apache-2.0
"""Stage, relink, and boot the package manager from a glibc stock release."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from make_work_disk import create_fat32
from package_p2_faults import boot_maintenance_guest, resources
from relink_release_xypm import FORMAT, LIBC, LINK_FLAGS
from task_smoke import send_bytes
from xos_app import check, sdk_notices
from xypm_format import canonical, load_json, require, sha_file
from xypm_image import Disk
from xypm_sdk_profile import relative_file

VERSION = b'xypm 0.4.0 (P3 offline repositories)'
REPLACED = b'[REPLACED_LIBC]'


def collect(args):
    release = load_json(args.release / 'release_manifest.json')
    kit = args.release / 'application-sdk'
    profile = load_json(kit / 'profile.json')
    require(sha_file(kit / 'profile.json') == release['application_sdk']['profile_file_sha256'],
            'release profile changed')
    sdk = kit / 'sdk'
    sysroot = (sdk / 'sysroot').resolve(strict=True)
    project, app, published = check(args.project.resolve(), sdk, profile)
    candidate_manifest = args.candidate / 'candidate_manifest.json'
    stock = args.candidate / 'stock'
    require(sha_file(candidate_manifest) == release['candidate_manifest_sha256'], 'candidate digest differs')
    require(app['id'] == 'xos.xypm' and sha_file(stock / 'xypm.elf') == release['xypm_sha256']
            == published['output_sha256'], 'released xypm differs')
    require(load_json(stock / 'build_receipt.json') == published, 'published application receipt differs')
    require(published['sdk_manifest_sha256'] == release['application_sdk']['sdk_manifest_sha256'],
            'xypm is bound to another SDK')

    backend_path = args.reference.parent / (args.reference.name + '.build')
    backend = load_json(backend_path / 'manifest.json')
    tools = published['binutils'] | {'g++': published['compiler']['sha256']}
    require(backend['status'] == 'static_program_linked'
            and backend['builder_sha256'] == published['backend_sha256']
            and backend['elf_sha256'] == sha_file(args.reference) == release['xypm_sha256']
            and backend['sdk_manifest_sha256'] == published['sdk_manifest_sha256']
            and backend['profile_binding']['profile_sha256'] == published['profile_sha256']
            and backend['compiler']['sha256'] == tools['g++']
            and {name: item['sha256'] for name, item in backend['binutils'].items()} == published['binutils'],
            'reconstructed backend does not bind the exact released executable')
    require(list(backend['sources'].values()) == [published['inputs'][name] for name in app['sources']],
            'reconstructed translation units differ from the release')
    steps = [step for step in backend['steps'] if step['name'] == 'link']
    require(len(steps) == 1 and steps[0]['exit_code'] == 0, 'missing successful backend link step')
    command = steps[0]['command']
    require(command[1] == '--sysroot=' + str(sysroot) and command[2].startswith('-B')
            and command.count('-o') == 1, 'unexpected backend link driver')
    options = command[3:]
    index = options.index('-o')
    del options[index:index + 2]
    plan, sources = [], {}
    sdk_artifacts = load_json(sdk / 'manifest.json')['artifacts']
    for option in options:
        if option in LINK_FLAGS:
            plan.append(option)
            continue
        path = Path(option)
        require(path.is_absolute() and path.suffix in ('.o', '.a', '.ld'), 'unexpected backend argument')
        if path.is_relative_to(sysroot):
            relative = path.relative_to(sysroot).as_posix()
            incoming = relative_file(sysroot, relative)
            require(sdk_artifacts[relative] == sha_file(incoming), 'link input differs from SDK')
            name = 'sysroot/' + relative
        else:
            incoming = relative_file(backend_path, path.name)
            require(path == incoming and path.name in {f'program_{i}.o' for i in range(len(app['sources']))},
                    'unexpected link object')
            name = 'objects/' + path.name
        require(name not in sources, 'duplicate file in link plan')
        sources[name] = incoming
        plan.append({'file': name})
    require(LIBC in sources, 'link plan omits libc')

    sources.update({'project/' + name: relative_file(project, name) for name in published['inputs']})
    sources.update({'licenses/' + name: file for file, name in sdk_notices(sdk, profile, 'cpp')})
    for name in ('relink_release_xypm.py', 'glibc_g1_probe.py', 'glibc_g1_deps.py', 'xypm_format.py'):
        sources['tools/' + name] = ROOT / 'scripts' / name
    sources.update({'receipt/release_manifest.json': args.release / 'release_manifest.json',
                    'receipt/sdk_manifest.json': sdk / 'manifest.json',
                    'receipt/profile.json': kit / 'profile.json',
                    'receipt/application.json': stock / 'build_receipt.json'})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    require(not args.output.exists() and not args.output.is_symlink(), 'choose absent materials output')
    with TemporaryDirectory(dir=args.output.parent) as temp:
        stage = Path(temp) / 'materials'
        for name, incoming in sources.items():
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(incoming, target)
        manifest = {'format': FORMAT, 'plan': plan, 'tools': tools, 'reference': release['xypm_sha256'],
                    'files': {name: sha_file(stage / name) for name in sorted(sources)}}
        (stage / 'manifest.json').write_bytes(canonical(manifest))
        stage.rename(args.output)
    print(sha_file(args.output / 'manifest.json'))


def guest(args):
    release = load_json(args.release / 'release_manifest.json')
    assets = args.release / 'images'
    image = assets / 'xos-install.iso'
    require(sha_file(image) == release['system']['iso']['sha256'], 'release ISO differs')
    require(sha_file(args.installed_disk) == args.installed_disk_sha256, 'installer guest disk differs')
    require(sha_file(args.original) == release['xypm_sha256'], 'detached xypm differs from release')
    args.output.mkdir(parents=True)
    with TemporaryDirectory(dir=args.output) as directory:
        work = Path(directory)
        with Disk(args.installed_disk, work, True) as installed:
            require(sha_file(installed.export('/usr/bin/xypm')) == release['xypm_sha256'],
                    'installed xypm differs from release')
        disk = work / 'guest.img'
        create_fat32(disk, 128)
        with Disk(disk, work) as fat:
            fat.command('import', '/original.elf', args.original)
            fat.command('import', '/replacement.elf', args.replacement)
        vm = boot_maintenance_guest(image, 'release_xypm_relink', disk)
        try:
            require(('build=' + release['system']['build_id']).encode() in vm.output, 'wrong guest system')
            baseline = resources(vm)
            for name, changed in (('original', False), ('replacement', True)):
                for flag, marker in (('--version', VERSION), ('list', b'No packages installed.')):
                    start = len(vm.output)
                    send_bytes(vm, f'exec-file /{name}.elf {flag}\r'.encode())
                    vm.expect_supervisor(start=start, timeout=90)
                    result = bytes(vm.output[start:])
                    require(marker in result and b'kind=exited code=0' in result
                            and (REPLACED in result) == (changed and flag == '--version'),
                            f'unexpected guest result for {name} {flag}')
                    require(resources(vm) == baseline, 'guest resources changed')
        finally:
            vm.close()
            (args.output / 'serial.log').write_bytes(vm.output)
        with Disk(disk, work, True) as fat:
            for name in ('original', 'replacement'):
                require(sha_file(fat.export('/' + name + '.elf')) == sha_file(getattr(args, name)), 'guest ELF changed')
    result = {'status': 'passed_subset', 'build_id': release['system']['build_id'],
              'iso_sha256': sha_file(image), 'release_manifest_sha256': sha_file(args.release / 'release_manifest.json'),
              'installed_disk_sha256': args.installed_disk_sha256,
              'original_sha256': sha_file(args.original), 'replacement_sha256': sha_file(args.replacement),
              'qemu': subprocess.check_output([os.environ.get('QEMU', 'qemu-system-x86_64'), '--version'],
                                              text=True).splitlines()[0],
              'resources': list(baseline), 'serial_sha256': sha_file(args.output / 'serial.log')}
    (args.output / 'report.json').write_bytes(canonical(result))
    print('PASS released xypm static relink and runtime substitution in guest')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for action, paths in ((collect, ('release', 'candidate', 'project', 'reference', 'output')),
                          (guest, ('release', 'original', 'replacement', 'installed-disk', 'output'))):
        step = sub.add_parser(action.__name__)
        step.set_defaults(run=action)
        for name in paths:
            step.add_argument('--' + name, type=Path, required=True)
        if action is guest:
            step.add_argument('--installed-disk-sha256', required=True)
    args = parser.parse_args()
    args.run(args)


if __name__ == '__main__':
    main()
