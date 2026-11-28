#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the installed host SDK, including the packaged C/C++ bytes in QEMU."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

VALIDATION = Path(__file__).resolve().parent
XOS = VALIDATION.parent
KIT = XOS / 'glibc'
sys.path[:0] = [str(VALIDATION / 'scripts'), str(VALIDATION / 'tests'), str(KIT / 'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from xypm_format import load_json, require, sha_file, verify_package
from xypm_sdk_profile import verify_profile


def run(command, log):
    with log.open('wb') as output:
        subprocess.run(list(map(str, command)), stdout=output, stderr=subprocess.STDOUT, check=True)


def guest_command(guest, command, marker, timeout=120):
    start = len(guest.output)
    for byte in command.encode() + b'\r':
        guest.process.stdin.write(bytes([byte]))
        guest.process.stdin.flush()
        time.sleep(0.003)
    guest.expect(marker, start=start, timeout=timeout)
    guest.expect(b'xsh> ', start=guest.output.index(marker, start), timeout=45)
    return bytes(guest.output[start:])


def smoke(output):
    require(os.environ.get('XOS_SDK') == str(KIT / 'sdk/sysroot'), 'default XOS_SDK is not glibc')
    require(Path(shutil.which('xos-app')).resolve() == KIT / 'xos-app', 'default xos-app is not this kit')
    output.mkdir(parents=True, exist_ok=False)
    profile = load_json(KIT / 'profile.json')
    binding = verify_profile(profile, 'glibc', KIT / 'sdk')
    release = load_json(XOS / 'host-sdk.json')
    require(sha_file(KIT / 'profile.json') == release['profile_sha256'], 'release profile differs')
    iso = XOS / 'boot/xos-install.iso'
    require(sha_file(iso) == release['system']['iso_sha256'], 'release ISO differs')
    report = {'schema': 1, 'status': 'failed', 'source_commit': release['source_commit'],
              'host_sdk_manifest_sha256': sha_file(XOS / 'host-sdk.json'),
              'base_sdk_sha256': release['base_sdk_sha256'], 'profile_sha256': release['profile_sha256'],
              'binding': binding, 'system': release['system'], 'applications': {},
              'execution': 'packaged ELF bytes; QEMU TCG; no guest network device'}
    guest = None
    try:
        disk = output / 'work.img'
        create_fat32(disk, 512)
        fat = VALIDATION / 'bin/work_disk_host'

        def transfer(operation, path, source=None):
            command = [fat, disk, operation, path]
            if source is not None:
                command.append(source)
            subprocess.run(list(map(str, command)), check=True, stdout=subprocess.DEVNULL)

        for path in ('/usr', '/usr/bin', '/state'):
            transfer('mkdir', path)
        seed = output / 'user.txt'
        seed.write_text('glibc-user-data\n')
        transfer('import', '/state/user.txt', seed)
        for language, suffix in (('c', 'c'), ('cpp', 'cpp')):
            project = output / language
            for step, arguments in (
                ('init', [project, '--id', 'hostsdk.' + language, '--language', language]),
                ('build', [project]), ('check', [project]),
                ('pack', [project, '--output', output / (language + '.xpk')]),
            ):
                run(['xos-app', step, *arguments], output / (language + '-' + step + '.log'))
                if step == 'init':
                    shutil.copyfile(VALIDATION / 'fixtures' / ('external.' + suffix),
                                    project / 'src' / ('main.' + suffix))
                    app = load_json(project / 'xos_app.json')
                    app['required_features'] = sorted(set(app['required_features']) | {'directories'} |
                                                      ({'threads'} if language == 'cpp' else set()))
                    (project / 'xos_app.json').write_text(json.dumps(app, indent=2) + '\n')
            package = output / (language + '.xpk')
            checked = verify_package(package, profile)
            item = next(item for item in checked['manifest']['files'] if item['role'] == 'executable')
            executable = output / (language + '.elf')
            with executable.open('xb') as stream:
                def capture(event, descriptor, data):
                    if event == 'data' and descriptor['path'] == item['path']:
                        stream.write(data)
                verify_package(package, profile, expected_sha256=checked['sha256'], sink=capture)
            require(sha_file(executable) == item['sha256'], 'extracted executable differs from package')
            transfer('import', '/usr/bin/kit_' + language, executable)
            report['applications'][language] = {
                'steps': ['init', 'build', 'check', 'pack', 'verify', 'extract'],
                'source_sha256': sha_file(project / 'src' / ('main.' + suffix)),
                'package_sha256': checked['sha256'], 'elf_sha256': item['sha256'],
                'build_receipt_sha256': sha_file(project / 'build/build_receipt.json')}
        guest = Guest(iso, 'host-sdk', iso=True, work_disk=disk, log_dir=output, qmp_enabled=False)
        guest.expect(b'xos64> ', timeout=90)
        require(('build=' + release['system']['build_id']).encode() in guest.output, 'wrong guest build ID')
        guest_command(guest, 'run', b'xsh> ', timeout=90)
        guest_command(guest, 'trace on', b'xsh: trace on')
        guest_command(guest, 'demo quiet', b'demo tasks')

        def resources():
            data = guest_command(guest, 'stats', b'[resources] free=')
            match = re.search(rb'free=(\d+) tasks=(\d+) completions=(\d+)', data)
            require(match is not None, 'missing guest resource counts')
            return list(map(int, match.groups()))

        baseline = resources()
        for language, marker in (('c', b'GLIBC_KIT_C_OK 2.44'),
                                 ('cpp', b'GLIBC_KIT_CPP_OK vector thread exception')):
            data = guest_command(guest, 'exec-file /usr/bin/kit_' + language, b'kind=exited code=0')
            require(marker in data, 'missing real application result')
            after = resources()
            require(after == baseline, 'application did not restore resource baseline')
            report['applications'][language].update(guest_exit_code=0, marker=marker.decode(),
                                                     resources_before=baseline, resources_after=after)
        guest_command(guest, 'sync', b'[files] sync=ok')
        guest.close()
        guest = None
        readback = output / 'user-after.txt'
        transfer('export', '/state/user.txt', readback)
        require(readback.read_bytes() == seed.read_bytes(), 'user data changed')
        report.update(status='passed', user_data_preserved=True,
                      serial_sha256=sha_file(output / 'host-sdk_serial.log'))
    finally:
        if guest is not None:
            guest.close()
        (output / 'qualification.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print('XOS glibc host SDK: C/C++ build, package, real guest and resources PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, default=Path('/work/sdk-smoke'))
    smoke(parser.parse_args().output.resolve())


if __name__ == '__main__':
    main()
