#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the built GNU/gnulib bytes in XOS and verify codec results offline."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes
from xypm_format import canonical, load_json, require, sha_file
from xypm_image import Disk, host_tool


PAYLOAD = bytes(range(256)) * 29 + b'GNU gzip on XOS\n' * 67
USER_DATA = b'issue-133 unrelated user data must survive\n'


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    build = args.gzip_build.resolve(strict=True)
    built = load_json(build / 'manifest.json')
    dash = load_json(args.dash_receipt)
    system = load_json(args.system_build / 'manifest.json')
    iso = args.system_build / 'xos-install.iso'
    require(built['status'] == 'built_not_run' and dash['status'] == 'built_not_run'
            and dash['profile'] == 'dash_glibc_preview'
            and dash['sdk_manifest_sha256'] == built['sdk_manifest_sha256'],
            'gzip and dash must be real builds from the same complete SDK')
    programs = {name: build / value['path'] for name, value in built['programs'].items()}
    programs['dash'] = ROOT / dash['elf']
    hashes = {name: sha_file(path) for name, path in programs.items()}
    require(hashes['dash'] == dash['sha256'], 'dash bytes differ from receipt')
    for name, value in built['programs'].items():
        require(hashes[name] == value['sha256'], 'gzip/gnulib bytes differ from build')
    require(all(sha_file(ROOT / name) == value for name, value in built['inputs'].items()),
            'GNU source recipe changed after build')
    require(sha_file(iso) == system['artifacts']['xos-install.iso']['sha256'], 'system ISO differs')
    # This is an independently built SDK paired with an unchanged baseline OS.
    # No kernel/native-service changes can be hidden behind that pairing.
    for name, digest in system['sources'].items():
        if name.startswith(('src/kernel/', 'src/boot/', 'src/shared/', 'src/user/')):
            require(sha_file(ROOT / name) == digest, 'baseline OS source differs: ' + name)
    dependencies = ('tests/gnu_gzip_guest.py', 'tests/boot_smoke.py',
                    'tests/process_smoke.py', 'tests/task_smoke.py',
                    'scripts/run_qemu.py', 'scripts/make_work_disk.py',
                    'scripts/xypm_image.py', 'scripts/xypm_format.py')
    runner_inputs = {name: sha_file(ROOT / name) for name in dependencies}
    disk_tool = host_tool()
    report = {'schema': 1, 'status': 'failed', 'suite': 'gnu_gzip_and_gnulib',
              'runner_sha256': sha_file(Path(__file__)), 'build_receipt_sha256': sha_file(build / 'manifest.json'),
              'runner_inputs': runner_inputs, 'disk_tool_sha256': sha_file(disk_tool),
              'dash_receipt_sha256': sha_file(args.dash_receipt),
              'sdk_manifest_sha256': built['sdk_manifest_sha256'], 'profile_sha256': built['profile_sha256'],
              'system_build_id': system['build_id'], 'system_manifest_sha256': sha_file(args.system_build / 'manifest.json'),
              'system_iso_sha256': sha_file(iso), 'programs': hashes,
              'baseline_os': 'unchanged kernel/native services; independent source-built glibc application SDK',
              'profile_limits': built['profile_limits'], 'cases': [], 'offline_checks': []}
    host_gzip = shutil.which('gzip')
    require(host_gzip is not None, 'independent host gzip is required')
    host_encoded = subprocess.check_output([host_gzip, '-n', '-c'], input=PAYLOAD)
    report['host_gzip'] = {'sha256': sha_file(host_gzip),
                           'version': subprocess.check_output([host_gzip, '--version'], text=True).splitlines()[0]}
    guest = None
    try:
        disk = output / 'work.img'
        create_fat32(disk, 512)
        with Disk(disk, output) as fat:
            for path in ('/usr', '/usr/bin', '/work', '/state'):
                fat.command('mkdir', path)
            for name, path in programs.items():
                fat.command('import', '/usr/bin/' + name, path)

            def fixture(name, data):
                path = output / ('fixture_' + name.replace('/', '_'))
                path.write_bytes(data)
                fat.command('import', '/work/' + name, path)

            fixture('plain', PAYLOAD)
            fixture('named', PAYLOAD)
            fixture('remove', PAYLOAD)
            fixture('host.gz', host_encoded)
            fixture('concat.gz', gzip.compress(b'first\n', mtime=0) + gzip.compress(b'second\n', mtime=0))
            malformed = bytearray(gzip.compress(PAYLOAD, mtime=0))
            malformed[-8] ^= 1
            fixture('crc.gz', malformed)
            fixture('truncated.gz', gzip.compress(PAYLOAD, mtime=0)[:-4])
            fixture('not_gzip', b'not a compressed stream\n')
            fixture('broken.gz', malformed)
            fixture('collision', PAYLOAD)
            fixture('collision.gz', USER_DATA)
            fixture('user.txt', USER_DATA)
            fixture('streams.sh', b'''set -e
/usr/bin/gnulib_consumer
/usr/bin/gzip -nc /work/plain > /work/from_guest.gz
/usr/bin/gzip -dc /work/host.gz > /work/from_host
/usr/bin/gzip -dc /work/concat.gz > /work/concat
/usr/bin/gzip -nc < /work/plain | /usr/bin/gzip -dc > /work/pipeline
echo GZIP_DASH_STREAMS_OK
''')
            fixture('errors.sh', b'''/usr/bin/gzip -t /work/crc.gz
test "$?" -eq 1 || exit 31
/usr/bin/gzip -t /work/truncated.gz
test "$?" -eq 1 || exit 32
/usr/bin/gzip -d /work/broken.gz
test "$?" -eq 1 || exit 33
/usr/bin/gzip -c /work/plain > /missing/output.gz
test "$?" -ne 0 || exit 34
/usr/bin/gzip -c /work/plain 1>&-
test "$?" -eq 1 || exit 35
/usr/bin/gzip -n /work/collision < /work/plain
test "$?" -eq 2 || exit 36
echo GZIP_DASH_ERRORS_OK
''')
        report['initial_disk_sha256'] = sha_file(disk)
        guest = Guest(iso, 'gnu_gzip', work_disk=disk, iso=True, log_dir=output, qmp_enabled=False)
        report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
        qemu = Path(shutil.which(guest.command[0]) or guest.command[0])
        report['qemu_sha256'] = sha_file(qemu)
        guest.expect(b'xos64> ', timeout=90)
        require(('build=' + system['build_id']).encode() in guest.output, 'wrong booted system')
        send_bytes(guest, b'run\r')
        guest.expect_supervisor(trace=True, timeout=90)
        command(guest, 'demo quiet', b'demo tasks', timeout=30)
        baseline = resources(guest)
        report['resource_baseline'] = list(baseline)

        def case(name, arguments, expected, marker=None, timeout=120):
            # Ordinary xsh launch inherits create authority for the nested
            # dash cases.  The historical exec-file entry deliberately does
            # not; do not mistake that expected restriction for a port bug.
            line = arguments
            data = command(guest, line, b'kind=exited code=', timeout=timeout)
            exits = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(\d+)', data)
            require(exits and int(exits[-1]) == expected, 'unexpected exit for ' + name)
            require(marker is None or marker in data, 'missing result for ' + name)
            after = resources(guest)
            require(after == baseline, 'resources not reclaimed after ' + name)
            report['cases'].append({'name': name, 'command': line, 'exit_code': expected,
                                    'resources_after': list(after), 'output_sha256': hashlib.sha256(data).hexdigest()})
            print(name + ': PASS', flush=True)

        case('gnulib_public_interfaces', '/usr/bin/gnulib_consumer', 0,
             b'GNULIB_XOS_OK progname wchar flags stat directory fd_limit=32')
        case('gzip_version', '/usr/bin/gzip --version', 0, b'gzip 1.14')
        case('gzip_profile_help', '/usr/bin/gzip --help', 0, b'XOS profile:')
        case('host_stream_integrity', '/usr/bin/gzip -t /work/host.gz', 0)
        case('named_compression_keep', '/usr/bin/gzip -nk /work/named', 0)
        case('named_compression_remove', '/usr/bin/gzip -n /work/remove', 0)
        case('named_decompression_remove', '/usr/bin/gzip -d /work/remove.gz', 0)
        case('bad_crc_rejected', '/usr/bin/gzip -t /work/crc.gz', 1, b'crc error')
        case('truncated_rejected', '/usr/bin/gzip -t /work/truncated.gz', 1)
        case('non_gzip_rejected', '/usr/bin/gzip -t /work/not_gzip', 1, b'not in gzip format')
        case('missing_input_rejected', '/usr/bin/gzip -k /work/missing', 1, b'No such file')
        case('dash_streams_and_pipe', '/usr/bin/dash /work/streams.sh', 0,
             b'GZIP_DASH_STREAMS_OK', timeout=180)
        case('dash_errors_and_cleanup', '/usr/bin/dash /work/errors.sh', 0,
             b'GZIP_DASH_ERRORS_OK', timeout=180)
        command(guest, 'sync', b'[files] sync=ok', timeout=30)
        guest.close()
        guest = None
        report['serial_sha256'] = sha_file(output / 'gnu_gzip_serial.log')

        with Disk(disk, output, True) as fat:
            for path in ('plain', 'named', 'remove', 'from_host', 'pipeline'):
                data = fat.export('/work/' + path).read_bytes()
                require(data == PAYLOAD, 'data mismatch: ' + path)
                report['offline_checks'].append({'path': '/work/' + path, 'sha256': hashlib.sha256(data).hexdigest()})
            for path in ('named.gz', 'from_guest.gz'):
                data = fat.export('/work/' + path).read_bytes()
                require(gzip.decompress(data) == PAYLOAD, 'host could not decode guest data: ' + path)
                require(subprocess.check_output([host_gzip, '-d', '-c'], input=data) == PAYLOAD,
                        'host GNU gzip could not decode guest data: ' + path)
                report['offline_checks'].append({'path': '/work/' + path, 'sha256': hashlib.sha256(data).hexdigest(),
                                                 'host_decode': 'passed'})
            require(fat.export('/work/concat').read_bytes() == b'first\nsecond\n', 'concatenated members differ')
            require(fat.export('/work/user.txt').read_bytes() == USER_DATA, 'unrelated user data changed')
            require(fat.export('/work/broken.gz').read_bytes() == bytes(malformed), 'invalid input was removed or changed')
            require(fat.export('/work/collision').read_bytes() == PAYLOAD, 'collision removed or changed its input')
            require(fat.export('/work/collision.gz').read_bytes() == USER_DATA, 'collision overwrote user data')
            require(fat.info('/work/broken') is None, 'failed named output was not removed')
            require(fat.info('/work/remove.gz') is None, 'successful named decompression did not remove its input')
            require(fat.info('/missing/output.gz') is None, 'failed output was created')
        require(all(sha_file(path) == hashes[name] for name, path in programs.items()), 'program changed during qualification')
        require(sha_file(iso) == report['system_iso_sha256'], 'baseline ISO changed during qualification')
        require(all(sha_file(ROOT / name) == digest for name, digest in runner_inputs.items())
                and sha_file(disk_tool) == report['disk_tool_sha256']
                and sha_file(qemu) == report['qemu_sha256']
                and sha_file(host_gzip) == report['host_gzip']['sha256'],
                'qualification runner or tool changed during the run')
        report.update(status='passed', resource_recovery=True, user_data_preserved=True,
                      malformed_input_preserved=True, partial_named_output_removed=True,
                      closed_stdout_rejected=True, existing_output_preserved=True,
                      concatenated_members=True, final_disk_sha256=sha_file(disk))
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        if guest is not None:
            guest.close()
        (output / 'report.json').write_bytes(canonical(report))
    print('GNU gzip/gnulib: all real guest and offline data checks PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('system-build', 'gzip-build', 'dash-receipt', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    run(parser.parse_args())


if __name__ == '__main__':
    main()
