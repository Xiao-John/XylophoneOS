# SPDX-License-Identifier: Apache-2.0
"""Run every installed daily utility before and after a detached libc relink."""

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
from xypm_format import canonical, confined, load_json, require, sha_file, verify_package
from xypm_image import Disk

MARKER = b'[DAILY_RELINK_EXIT]'
PROBE = r"""set -e
run() {
    tool=$1
    shift
    printf 'DAILY_BEGIN=%s\n' "$tool"
    "/usr/bin/$tool" "$@"
    printf 'DAILY_END=%s\n' "$tool"
}
folder=/tmp/daily-relink
run mkdir "$folder"
printf 'first\nsecond\n' > "$folder/data"
run basename "$folder/data"
run dirname "$folder/data"
run cat "$folder/data"
run cp "$folder/data" "$folder/copy"
run mv "$folder/copy" "$folder/moved"
run head -n 1 "$folder/moved"
run tail -n 1 "$folder/moved"
run tee "$folder/tee" < "$folder/moved"
run wc -l "$folder/tee"
run ls -1 "$folder"
run rm "$folder/data" "$folder/moved" "$folder/tee"
run rmdir "$folder"
printf 'DAILY_RELINK_OK\n'
"""
EXPECT = {
    'basename': rb'data',
    'dirname': rb'/tmp/daily-relink',
    'cat': rb'first\nsecond',
    'head': rb'first',
    'tail': rb'second',
    'tee': rb'first\nsecond',
    'wc': rb' *2 /tmp/daily-relink/tee',
    'ls': rb'data\nmoved\ntee',
    'mkdir': rb'', 'cp': rb'', 'mv': rb'', 'rm': rb'', 'rmdir': rb'',
}


def disk_sha(fat, path):
    exported = fat.export(path)
    try:
        return sha_file(exported)
    finally:
        exported.unlink()


def run_phase(iso, disk, build_id, output, substituted):
    phase = 'replacement' if substituted else 'original'
    vm = boot_maintenance_guest(iso, 'release_daily_relink_' + phase, disk)
    try:
        require(('build=' + build_id).encode() in vm.output, 'wrong released system')
        baseline = resources(vm)
        start = len(vm.output)
        send_bytes(vm, b'dash /relink_probe.sh\r')
        vm.expect_supervisor(start=start, timeout=150)
        response = bytes(vm.output[start:]).replace(b'\r\n', b'\n')
        pairs = re.findall(rb'^DAILY_BEGIN=([a-z]+)\n(.*?)^DAILY_END=\1$', response, re.DOTALL | re.MULTILINE)
        require(len(pairs) == len(EXPECT) and {name.decode() for name, _ in pairs} == set(EXPECT)
                and b'\nDAILY_RELINK_OK\n' in response and b'kind=exited code=0' in response,
                'incomplete daily guest run')
        outputs = {}
        for name, data in pairs:
            name = name.decode()
            require(data.splitlines().count(MARKER) == int(substituted), 'wrong exit observation: ' + name)
            lines = [line for line in data.splitlines() if line != MARKER and not line.startswith((b'[process] ', b'[task] '))]
            observed = b'\n'.join(lines)
            require(re.fullmatch(EXPECT[name], observed) is not None, 'wrong utility output: ' + name)
            outputs[name] = observed.decode()
        require(resources(vm) == baseline, 'unreclaimed guest resources')
        return {'resources': list(baseline), 'outputs': outputs, 'exit_markers': response.count(MARKER)}
    finally:
        vm.close()
        (output / (phase + '.serial')).write_bytes(vm.output)


def check(args):
    release_path = args.release / 'release_manifest.json'
    require(sha_file(release_path) == args.release_sha256, 'release manifest differs')
    release = load_json(release_path)
    profile_path = args.release / 'application-sdk/profile.json'
    require(sha_file(profile_path) == release['application_sdk']['profile_file_sha256'], 'release profile differs')
    package = args.release / 'packages/daily.xpk'
    manifest = verify_package(package, load_json(profile_path), expected_sha256=release['daily_sha256'])['manifest']
    want = {Path(item['path']).name: item['sha256'] for item in manifest['files'] if item['role'] == 'executable'}
    require(manifest['id'] == 'xos.daily_utilities' and set(want) == set(EXPECT), 'wrong released utilities')
    changes = load_json(args.relink / 'replacement.json')
    require(sha_file(args.relink / 'replacement.json') == args.replacement_sha256
            and set(changes) == set(want) and all(changes[name] != digest for name, digest in want.items()),
            'replacement output receipt differs')
    for name, digest in want.items():
        require(sha_file(confined(args.relink, 'original/' + name)) == digest
                and sha_file(confined(args.relink, 'replacement/' + name)) == changes[name],
                'relinked utility differs: ' + name)
    installer = args.release / 'images/xos-install-dash.iso'
    ordinary = args.release / 'images/xos-install.iso'
    require(sha_file(installer) == release['installer_iso']['sha256']
            and sha_file(ordinary) == release['system']['iso']['sha256'], 'release ISO differs')
    build_id = release['system']['build_id']
    args.output.mkdir(parents=True)
    with TemporaryDirectory(dir=args.output) as folder:
        work = Path(folder)
        disk = work / 'install.img'
        create_fat32(disk, 512)
        script = work / 'probe.sh'
        script.write_text(PROBE)
        with Disk(disk, work) as fat:
            fat.command('mkdir', '/tmp')
            fat.command('import', '/relink_probe.sh', script)
        vm = Guest(installer, 'release_daily_relink_install', work_disk=disk, iso=True, log_dir=args.output)
        try:
            vm.expect(b'xos64> ', timeout=40)
            send_bytes(vm, b'run\r')
            vm.expect(b'[files] bundle packages installed', timeout=360)
            vm.expect_supervisor(timeout=360)
            require(('build=' + build_id).encode() in vm.output
                    and b'xypm-recover: committed transaction cleaned' in vm.output, 'wrong installer or incomplete commit')
        finally:
            vm.close()
            (args.output / 'installer.serial').write_bytes(vm.output)
        with Disk(disk, work, True) as fat:
            require(all(disk_sha(fat, '/usr/bin/' + name) == digest for name, digest in want.items()),
                    'actual installed daily ELF differs')
        original = run_phase(ordinary, disk, build_id, args.output, False)
        with Disk(disk, work) as fat:
            for name, digest in want.items():
                path = '/usr/bin/' + name
                require(disk_sha(fat, path) == digest, 'installed utility changed: ' + name)
                fat.command('remove', path)
                fat.command('import', path, confined(args.relink, 'replacement/' + name))
        replacement = run_phase(ordinary, disk, build_id, args.output, True)
        with Disk(disk, work, True) as fat:
            require(all(disk_sha(fat, '/usr/bin/' + name) == digest for name, digest in changes.items())
                    and disk_sha(fat, '/relink_probe.sh') == sha_file(script), 'replacement executable or probe changed')
    require(original['outputs'] == replacement['outputs'] and replacement['exit_markers'] == len(want),
            'daily outputs or marker count changed')
    result = {'status': 'passed_subset', 'build_id': build_id, 'release_sha256': args.release_sha256,
              'package_sha256': release['daily_sha256'], 'package_receipt_sha256': manifest['build_receipt']['sha256'],
              'installer_iso_sha256': sha_file(installer), 'ordinary_iso_sha256': sha_file(ordinary),
              'original': original, 'replacement': replacement, 'replacement_sha256': args.replacement_sha256,
              'qemu': subprocess.check_output([os.environ.get('QEMU', 'qemu-system-x86_64'), '--version'],
                                              text=True).splitlines()[0],
              'serial_sha256': {phase: sha_file(args.output / (phase + '.serial'))
                                for phase in ('installer', 'original', 'replacement')},
              'test_sha256': sha_file(Path(__file__))}
    (args.output / 'report.json').write_bytes(canonical(result))
    print('PASS installer daily utilities and all replacement links in ordinary guests')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('release', 'relink', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('release-sha256', 'replacement-sha256'):
        parser.add_argument('--' + name, required=True)
    check(parser.parse_args())


if __name__ == '__main__':
    main()
