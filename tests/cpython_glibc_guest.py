# SPDX-License-Identifier: Apache-2.0
"""Run the exact static glibc CPython core from the CLI on a private XOS disk."""

import argparse
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from glibc_static_guest import system_sources
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes
from xypm_format import canonical, load_json, require, sha_file
from xypm_image import Disk
from xypm_sdk_profile import verify_profile

FIXTURE = ROOT / 'tests/fixtures/cpython_glibc/startup_probe.py'
MARKERS = ('CPYTHON_G4_START 3.14.9 xos', 'CPYTHON_G4_CLOCK_PASS', 'CPYTHON_G4_THREADS_PASS')


def stage_lib(archive, version, temporary, fat):
    prefix = 'Python-' + version + '/Lib/'
    result = {}
    with tarfile.open(archive) as bundle:
        for member in bundle:
            path = member.name.removeprefix(prefix)
            if not member.isfile() or path == member.name:
                continue
            name = Path(path)
            if path != 'os.py' and (name.parent != Path('encodings') or name.suffix != '.py'):
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
    require({'os.py', 'encodings/__init__.py', 'encodings/utf_8.py'} <= result.keys(),
            'incomplete interpreter startup modules')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-build', type=Path, required=True)
    parser.add_argument('--cpython-build', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--glibc-profile', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sys_path = args.system_build / 'manifest.json'
    sysmeta = load_json(sys_path)
    image = args.system_build / 'xos-install.iso'
    build_path = args.cpython_build / 'py0a_report.json'
    build = load_json(build_path)
    elf = args.cpython_build / 'target_build/python.exe'
    lock = load_json(ROOT / 'src/ports/cpython/source_lock.json')
    profile = load_json(args.glibc_profile)

    def verify():
        require(system_sources() == sysmeta['sources']
                and sha_file(image) == sysmeta['artifacts']['xos-install.iso']['sha256'],
                'ordinary system or source snapshot differs')
        require(build['status'] == 'built_not_run' and build['runtime_family'] == 'glibc'
                and sha_file(elf) == build['executable']['sha256'], 'CPython CLI build or executable differs')
        require(lock['sha256'] == build['source_archive_sha256'] == sha_file(args.archive)
                and lock['version'] == build['version'], 'CPython archive differs')
        require(profile['sdk_binding']['sdk_manifest_sha256'] == build['sdk_manifest_sha256']
                and sha_file(args.glibc_profile) == build['profile_file_sha256']
                and verify_profile(profile, 'glibc', args.sdk) == build['sdk_binding'],
                'CPython SDK or glibc profile differs')

    verify()
    report = {'status': 'failed', 'build_receipt_sha256': sha_file(build_path),
              'system_build_id': sysmeta['build_id'], 'system_manifest_sha256': sha_file(sys_path),
              'image_sha256': sha_file(image), 'elf_sha256': sha_file(elf),
              'sdk_manifest_sha256': build['sdk_manifest_sha256'],
              'profile_sha256': build['profile_file_sha256'], 'probe_sha256': sha_file(FIXTURE),
              'checks': [], 'not_run': build['unqualified']}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='cpython_glibc_guest_') as folder:
            temporary = Path(folder)
            disk = temporary / 'work.img'
            create_fat32(disk, 512)
            with Disk(disk, temporary) as fat:
                for path in ('/usr', '/usr/bin', '/usr/lib', '/usr/lib/python3.14',
                             '/usr/lib/python3.14/encodings', '/tests'):
                    fat.command('mkdir', path)
                fat.command('import', '/usr/bin/python3', elf)
                fat.command('import', '/tests/g4.py', FIXTURE)
                report['stdlib'] = stage_lib(args.archive, build['version'], temporary, fat)

            guest = Guest(image, 'cpython_glibc_cli', work_disk=disk, iso=True)
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
            report['after'] = resources(guest)
            require(report['after'] == report['baseline'], 'CPython guest resource drift')
        verify()
        require(sha_file(build_path) == report['build_receipt_sha256'] and sha_file(FIXTURE) == report['probe_sha256'],
                'CPython receipt or probe changed during the guest')
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
