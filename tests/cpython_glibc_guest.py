# SPDX-License-Identifier: Apache-2.0
"""Run the exact static glibc CPython core from the CLI on a private XOS disk."""

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_cpython_glibc import glibc_openssl_binding
from glibc_static_guest import system_sources
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes
from xypm_format import canonical, load_json, require, sha_file
from xypm_image import Disk
from xypm_sdk_profile import metadata_snapshot, verify_profile

FIXTURE = ROOT / 'tests/fixtures/cpython_glibc/startup_probe.py'
HASHLIB_FIXTURE = FIXTURE.with_name('openssl_hashlib.py')
MARKERS = ('CPYTHON_G4_START 3.14.9 xos', 'CPYTHON_G4_CLOCK_PASS', 'CPYTHON_G4_THREADS_PASS')
HASHLIB_MARKER = b'CPYTHON_G4_OPENSSL_HASHLIB_PASS sha256 hmac pbkdf2 scrypt reject'


def stage_lib(archive, version, temporary, fat, *, with_hashlib=False):
    prefix = 'Python-' + version + '/Lib/'
    required = {'os.py', 'encodings/__init__.py', 'encodings/utf_8.py'}
    selected = {'os.py', 'hashlib.py'} if with_hashlib else {'os.py'}
    required.update(selected)
    result = {}
    with tarfile.open(archive) as bundle:
        for member in bundle:
            path = member.name.removeprefix(prefix)
            if not member.isfile() or path == member.name:
                continue
            name = Path(path)
            if path not in selected and (name.parent != Path('encodings') or name.suffix != '.py'):
                continue
            require(path not in result, 'duplicate standard library input: ' + path)
            local = temporary / 'stdlib' / path
            local.parent.mkdir(parents=True, exist_ok=True)
            data = bundle.extractfile(member)
            require(data is not None, 'unreadable standard library entry: ' + path)
            with data:
                local.write_bytes(data.read())
            fat.command('import', '/usr/lib/python3.14/' + path, local)
            result[path] = sha_file(local)
    require(required <= result.keys(), 'incomplete interpreter probe modules')
    return result


def stage_input(source, target, expected):
    shutil.copyfile(source, target)
    require(sha_file(target) == expected, 'guest input changed before staging: ' + str(source))
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-build', type=Path, required=True)
    parser.add_argument('--system-source', type=Path, default=ROOT)
    parser.add_argument('--cpython-build', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--glibc-profile', type=Path, required=True)
    parser.add_argument('--openssl-build', type=Path, help='bound OpenSSL build for the optional static _hashlib probe')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sys_path = args.system_build / 'manifest.json'
    sysmeta, sys_digest = metadata_snapshot(sys_path)
    image = args.system_build / 'xos-install.iso'
    build_path = args.cpython_build / 'py0a_report.json'
    build, build_digest = metadata_snapshot(build_path)
    elf = args.cpython_build / 'target_build/python.exe'
    lock = load_json(ROOT / 'src/ports/cpython/source_lock.json')
    profile, profile_digest = metadata_snapshot(args.glibc_profile)
    with_hashlib = '_hashlib' in build['static_extensions']
    require(with_hashlib == bool(args.openssl_build), 'OpenSSL build required only for the _hashlib candidate')

    def verify():
        require(system_sources(args.system_source.resolve(strict=True)) == sysmeta['sources']
                and sha_file(image) == sysmeta['artifacts']['xos-install.iso']['sha256'],
                'ordinary system or source snapshot differs')
        require(build['status'] == 'built_not_run' and build['runtime_family'] == 'glibc'
                and sha_file(elf) == build['executable']['sha256'], 'CPython CLI build or executable differs')
        require(lock['sha256'] == build['source_archive_sha256'] == sha_file(args.archive)
                and lock['version'] == build['version'], 'CPython archive differs')
        require(profile['sdk_binding']['sdk_manifest_sha256'] == build['sdk_manifest_sha256']
                and profile_digest == build['profile_file_sha256']
                and sha_file(args.glibc_profile) == profile_digest
                and verify_profile(profile, 'glibc', args.sdk) == build['sdk_binding'],
                'CPython SDK or glibc profile differs')
        if with_hashlib:
            require(glibc_openssl_binding(args.openssl_build, build['sdk_binding'], build['sdk_manifest_sha256'],
                                          profile_digest) == build['openssl'], 'CPython OpenSSL binding changed')

    verify()
    report = {'status': 'failed', 'build_receipt_sha256': build_digest,
              'system_build_id': sysmeta['build_id'], 'system_manifest_sha256': sys_digest,
              'image_sha256': sysmeta['artifacts']['xos-install.iso']['sha256'],
              'elf_sha256': build['executable']['sha256'],
              'sdk_manifest_sha256': build['sdk_manifest_sha256'],
              'profile_sha256': build['profile_file_sha256'], 'probe_sha256': sha_file(FIXTURE),
              'checks': [], 'not_run': build['unqualified']}
    if with_hashlib:
        report['hashlib_probe_sha256'] = sha_file(HASHLIB_FIXTURE)
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='cpython_glibc_guest_') as folder:
            temporary = Path(folder)
            guest_image = stage_input(image, temporary / 'system.iso', report['image_sha256'])
            guest_elf = stage_input(elf, temporary / 'python3', report['elf_sha256'])
            guest_archive = stage_input(args.archive, temporary / 'cpython.tar.xz', lock['sha256'])
            guest_probe = stage_input(FIXTURE, temporary / 'g4.py', report['probe_sha256'])
            disk = temporary / 'work.img'
            create_fat32(disk, 512)
            with Disk(disk, temporary) as fat:
                for path in ('/usr', '/usr/bin', '/usr/lib', '/usr/lib/python3.14',
                             '/usr/lib/python3.14/encodings', '/tests'):
                    fat.command('mkdir', path)
                fat.command('import', '/usr/bin/python3', guest_elf)
                fat.command('import', '/tests/g4.py', guest_probe)
                if with_hashlib:
                    probe = stage_input(HASHLIB_FIXTURE, temporary / 'hashlib_probe.py', report['hashlib_probe_sha256'])
                    fat.command('import', '/tests/hashlib_probe.py', probe)
                report['stdlib'] = stage_lib(guest_archive, build['version'], temporary, fat, with_hashlib=with_hashlib)

            guest = Guest(guest_image, 'cpython_glibc_cli', work_disk=disk, iso=True)
            report['qemu'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=40)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=40)
            command(guest, 'demo quiet', b'demo tasks')
            command(guest, 'audio stop', b'audio: service stopped')
            report['baseline'] = resources(guest)
            start = len(guest.output)
            send_bytes(guest, b'exec-file /usr/bin/python3 -B -S /tests/g4.py\r')
            guest.expect(b'kind=exited code=', start=start, timeout=180)
            guest.expect_supervisor(start=start, timeout=30)
            captured = bytes(guest.output[start:])
            for marker in MARKERS:
                require(marker.encode() in captured, 'missing CPython marker: ' + marker)
                report['checks'].append(marker)
            require(re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', captured) == [b'0'],
                    'unexpected CPython process status')
            if with_hashlib:
                captured = command(guest, 'exec-file /usr/bin/python3 -B -S /tests/hashlib_probe.py', b'kind=', timeout=180)
                require(captured.replace(b'\r', b'').splitlines().count(HASHLIB_MARKER) == 1
                        and re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', captured) == [b'0'],
                        'OpenSSL hashlib probe failed')
                report['checks'].append(HASHLIB_MARKER.decode())
                require(sha_file(HASHLIB_FIXTURE) == report['hashlib_probe_sha256'], 'hashlib probe changed')
            report['after'] = resources(guest)
            require(report['after'] == report['baseline'], 'CPython guest resource drift')
        verify()
        require(sha_file(build_path) == build_digest and sha_file(sys_path) == sys_digest
                and sha_file(FIXTURE) == report['probe_sha256'],
                'CPython receipt, system manifest or probe changed during the guest')
        report['status'] = 'passed_subset'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if guest is not None:
            guest.close()
            serial = output / 'serial.log'
            serial.write_bytes(guest.output)
            report['serial_sha256'] = sha_file(serial)
        (output / 'report.json').write_bytes(canonical(report))


if __name__ == '__main__':
    main()
