# SPDX-License-Identifier: Apache-2.0
"""Run the selected glibc applications and GNU Make from one installed XOS disk."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from cpython_py0b_smoke import run
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes
from work_disk import transfer
from xypm_format import load_json, require, sha_file

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate', 'sdk-kit', 'c-xpk', 'cxx-xpk', 'make-manifest', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = args.candidate / 'candidate_manifest.json'
    candidate = load_json(receipt)
    binding = candidate['application_sdk']
    profile = args.sdk_kit / 'profile.json'
    image = args.candidate / 'system/xos-install-dash.iso'
    install_receipt = args.candidate / 'system/install_manifest.json'
    installed = load_json(install_receipt)
    make = load_json(args.make_manifest)
    make_elf = args.make_manifest.parent / make['elf']['path']
    require(candidate['installer_guest_qualification'] == 'passed'
            and sha_file(image) == candidate['artifacts']['system/xos-install-dash.iso']
            and sha_file(install_receipt) == candidate['artifacts']['system/install_manifest.json']
            and installed['build_id'] == candidate['build_id'], 'installer receipt does not bind the ISO')
    require(sha_file(profile) == binding['profile_file_sha256'] == make['profile_sha256']
            and sha_file(args.sdk_kit / 'sdk/manifest.json') == binding['sdk_manifest_sha256'] == make['sdk_manifest_sha256']
            and sha_file(make_elf) == make['elf']['sha256'], 'Make and the installer must use the same SDK')

    report = {'status': 'failed', 'candidate_source': candidate['source_commit'],
               'build_id': candidate['build_id'], 'candidate_manifest_sha256': sha_file(receipt),
               'iso_sha256': sha_file(image), 'sdk_manifest_sha256': binding['sdk_manifest_sha256'],
               'profile_sha256': sha_file(profile), 'make_sha256': sha_file(make_elf),
               'make_manifest_sha256': sha_file(args.make_manifest),
               'packages': {path.name: sha_file(path) for path in (args.c_xpk, args.cxx_xpk)},
               'runner_sha256': sha_file(Path(__file__)), 'boots': []}
    try:
        with tempfile.TemporaryDirectory(prefix='xos_cold_matrix_') as lab:
            work = Path(lab)
            disk = work / 'initial.img'
            create_fat32(disk, 512)
            for package in (args.c_xpk, args.cxx_xpk):
                next_disk = work / (package.stem + '.img')
                subprocess.run([sys.executable, str(ROOT / 'scripts/xypm.py'), 'install', str(package),
                                '--offline', '--profile', str(profile), '--image', str(disk),
                                '--output-image', str(next_disk)], check=True, stdout=subprocess.DEVNULL)
                disk = next_disk
            transfer(disk, 'mkdir', '/state')
            fixtures = {'user.txt': 'glibc-user-data\n',
                        'apps.sh': 'set -e\nkit_c\n/usr/bin/kit_cpp\n'
                                   'gmake -r -B -f /state/Makefile all\necho XOS_COLD_APP_MATRIX_OK\n',
                        'Makefile': '.PHONY: all\nall:\n\t@/usr/bin/kit_c\n'
                                    "\t@printf '%s\\n' 'XOS_MAKE_RECIPE_OK';\n"}
            for name, content in fixtures.items():
                path = work / name
                path.write_text(content)
                transfer(disk, 'import', '/state/' + name, path)
            transfer(disk, 'import', '/usr/bin/gmake', make_elf)
            for index in range(2):
                label = f'cold_matrix_{index + 1}'
                guest = Guest(image, label, work_disk=disk, log_dir=args.output)
                try:
                    report['qemu'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
                    guest.expect(b'xos64> ', timeout=45)
                    offset = len(guest.output)
                    send_bytes(guest, b'run\r')
                    if index == 0:
                        guest.expect(b'[files] dash installed', start=offset, timeout=90)
                    guest.expect_supervisor(trace=True, start=offset, timeout=60)
                    before = resources(guest)
                    start = len(guest.output)
                    output = run(guest, 'dash /state/apps.sh', timeout=180)
                    milestones = ('GLIBC_KIT_C_OK 2.44', 'GLIBC_KIT_CPP_OK vector thread exception',
                                  'XOS_MAKE_RECIPE_OK', 'XOS_COLD_APP_MATRIX_OK', 'kind=exited code=0')
                    require(all(marker in output for marker in milestones)
                            and output.count(milestones[0]) == 2, f'Unexpected application outcome in {label}')
                    after = resources(guest)
                    transition = bytes(guest.output[start:])
                    retired = {int(pid) for pid in re.findall(rb'event=killed_by_supervisor pid=(\d+)', transition)}
                    reclaimed = {int(pid): int(pages) for pid, pages in
                                 re.findall(rb'event=reclaimed pid=(\d+) pages=(\d+)', transition)}
                    require(retired in (set(), {1, 2, 3, 4}) and retired <= reclaimed.keys(),
                            'unexpected task retirement during the initial installation launch')
                    require(after == (before[0] + sum(reclaimed[pid] for pid in retired),
                                      before[1] - len(retired), before[2]), 'dash did not restore its resources')
                    require('GNU Make 4.4.1' in run(guest, 'gmake --version', timeout=45)
                            and resources(guest) == after, 'GNU Make did not return to the resource baseline')
                    command(guest, 'sync', b'[files] sync=ok', timeout=45)
                    report['boots'].append({'outcome': 'passed', 'before': before, 'after': after,
                                            'retired_demo_tasks': sorted(retired), 'markers': milestones})
                finally:
                    guest.close()
                    serial = args.output / (label + '.serial.log')
                    serial.write_bytes(bytes(guest.output))
                    report.setdefault('serial_sha256', {})[label] = sha_file(serial)
            for path, expected in [('/usr/bin/dash', installed['dash_sha256']),
                                   ('/usr/bin/gmake', make['elf']['sha256']),
                                   ('/state/user.txt', sha_file(work / 'user.txt'))]:
                readback = work / 'readback'
                transfer(disk, 'export', path, readback)
                require(sha_file(readback) == expected, f'changed file on final work disk: {path}')
                readback.unlink()
            report['status'] = 'passed_subset'
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'])


if __name__ == '__main__':
    main()
