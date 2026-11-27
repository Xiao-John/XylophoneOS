# SPDX-License-Identifier: Apache-2.0
"""Exercise the released and relinked Dash from the same installer-created FAT32 disk."""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_smoke import Guest
from make_work_disk import create_fat32
from package_p2_faults import boot_maintenance_guest, resources
from task_smoke import send_bytes
from xypm_format import canonical, load_json, require, sha_file
from xypm_image import Disk

DASH = '/usr/bin/dash'
MARKER = 773355


def shell_check(image, build_id, disk, output, phase):
    vm = boot_maintenance_guest(image, 'release_dash_relink_' + phase, disk)
    try:
        require(('build=' + build_id).encode() in vm.output, 'wrong released system')
        start = len(vm.output)
        send_bytes(vm, b'type dash\r')
        vm.expect(b'dash -> /usr/bin/dash', start=start, timeout=30)
        vm.expect_supervisor(start=start, timeout=30)
        baseline = resources(vm)
        start = len(vm.output)
        send_bytes(vm, b'dash /probe.sh\r')
        vm.expect_supervisor(start=start, timeout=90)
        response = bytes(vm.output[start:])
        pid = re.search(rb'\nDASH_RELINK_PID=(\d+)\r?\n', response)
        require(pid is not None and b'\nDASH_BUILTIN=ok' in response
                and b'hello from file' in response and b'\nDASH_EXTERNAL=ok' in response
                and b'kind=exited code=0' in response, 'Dash script or child failed')
        value = int(pid[1])
        require((value == MARKER) if phase == 'replacement' else (0 < value < MARKER),
                'unexpected Dash runtime PID')
        require(resources(vm) == baseline, 'unreclaimed guest resources')
        return {'pid': value, 'resources': list(baseline)}
    finally:
        vm.close()
        (output / (phase + '.log')).write_bytes(vm.output)


def check(args):
    release_path = args.release / 'release_manifest.json'
    require(sha_file(release_path) == args.release_sha256, 'release manifest differs')
    release = load_json(release_path)
    system_manifest = args.system / 'manifest.json'
    require(sha_file(system_manifest) == release['system']['manifest_sha256'], 'system manifest differs')
    assets = args.release / 'images'
    installer = assets / 'xos-install-dash.iso'
    ordinary = assets / 'xos-install.iso'
    require(sha_file(installer) == release['installer_iso']['sha256']
            and sha_file(ordinary) == release['system']['iso']['sha256'], 'release ISO differs')
    build_id = release['system']['build_id']
    hello = args.system / 'user_hello.image.elf'
    require(sha_file(hello) == load_json(system_manifest)['artifacts'][hello.name]['sha256'],
            'external ELF differs from the released system probe')
    original = sha_file(args.original)
    replacement = sha_file(args.replacement)
    require(original == release['dash_sha256'] and replacement == args.replacement_sha256 != original,
            'Dash input differs from the selected release or replacement')
    args.output.mkdir(parents=True)
    with TemporaryDirectory(dir=args.output) as folder:
        work = Path(folder)
        disk = work / 'install.img'
        create_fat32(disk, 512)
        script = work / 'probe.sh'
        script.write_bytes(b"set -e\nprintf 'DASH_RELINK_PID=%s\\n' \"$$\"\n"
                           b"printf 'DASH_BUILTIN=%s\\n' \"$(printf ok)\"\n"
                           b"/hello.elf\nprintf 'DASH_EXTERNAL=ok\\n'\n")
        with Disk(disk, work) as fat:
            fat.command('import', '/hello.elf', hello)
            fat.command('import', '/probe.sh', script)
        vm = Guest(installer, 'release_dash_relink_install', work_disk=disk, iso=True, log_dir=args.output)
        try:
            vm.expect(b'xos64> ', timeout=40)
            send_bytes(vm, b'run\r')
            vm.expect(b'[files] bundle installed: /usr/bin/dash', timeout=360)
            vm.expect_supervisor(timeout=360)
            require(('build=' + build_id).encode() in vm.output, 'wrong installer system')
        finally:
            vm.close()
            (args.output / 'installer.log').write_bytes(vm.output)
        with Disk(disk, work, True) as fat:
            require(sha_file(fat.export(DASH)) == original, 'installer wrote a different Dash')
        baseline = shell_check(ordinary, build_id, disk, args.output, 'original')
        with Disk(disk, work) as fat:
            require(sha_file(fat.export(DASH)) == original, 'original changed during guest run')
            fat.command('remove', DASH)
            fat.command('import', DASH, args.replacement)
            require(sha_file(fat.export(DASH)) == replacement, 'offline replacement differed')
        changed = shell_check(ordinary, build_id, disk, args.output, 'replacement')
        with Disk(disk, work, True) as fat:
            require(sha_file(fat.export(DASH)) == replacement, 'replacement changed during guest run')
            require(sha_file(fat.export('/hello.elf')) == sha_file(hello)
                    and sha_file(fat.export('/probe.sh')) == sha_file(script), 'guest probe inputs changed')

    result = {'status': 'passed_subset', 'build_id': build_id, 'release_manifest_sha256': args.release_sha256,
              'installer_iso_sha256': sha_file(installer), 'ordinary_iso_sha256': sha_file(ordinary),
              'ordinary_system_manifest_sha256': sha_file(system_manifest), 'guest_dash_path': DASH,
              'original_sha256': original, 'replacement_sha256': replacement, 'external_sha256': sha_file(hello),
              'checks': {'original': baseline, 'replacement': changed},
              'qemu': subprocess.check_output([os.environ.get('QEMU', 'qemu-system-x86_64'), '--version'],
                                              text=True).splitlines()[0],
              'serial_sha256': {phase: sha_file(args.output / (phase + '.log'))
                                for phase in ('installer', 'original', 'replacement')},
              'test_sha256': sha_file(Path(__file__))}
    (args.output / 'report.json').write_bytes(canonical(result))
    print('PASS released installer Dash and actual runtime replacement in ordinary guest')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('release', 'system', 'original', 'replacement', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    for name in ('release-sha256', 'replacement-sha256'):
        parser.add_argument('--' + name, required=True)
    check(parser.parse_args())


if __name__ == '__main__':
    main()
