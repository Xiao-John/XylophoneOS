#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the profile-bound OpenSSL static probe in an ordinary, offline XOS guest."""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_smoke import Guest
from build_glibc_program import verify_elf
from build_openssl_target import BUILDER, LIBS, LOCK, PROBE
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import pump, send_bytes
from verify_glibc_source import digest
from work_disk import transfer
from xypm_sdk_profile import metadata_snapshot, verify_profile


MARKER = b'XOS_OPENSSL_STATIC_OK sha256 rand tls13 verified_exchange hostname_reject'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_inputs(args, report):
    receipt_path = args.build / 'report.json'
    receipt, receipt_hash = metadata_snapshot(receipt_path)
    require(receipt['status'] == 'static_sdk_and_probe_linked', 'OpenSSL is not a completed static build')
    require(digest(LOCK) == receipt['source_lock_sha256'], 'OpenSSL source lock changed')
    require(digest(BUILDER) == receipt['builder_sha256'], 'OpenSSL build script changed')
    require(digest(PROBE) == receipt['fixture_sha256'], 'OpenSSL source fixture changed')
    profile, profile_hash = metadata_snapshot(args.profile, receipt['sdk_profile_sha256'])
    require(digest(args.sdk / 'manifest.json') == receipt['sdk_manifest_sha256'], 'SDK manifest changed')
    require(verify_profile(profile, 'glibc', args.sdk) == receipt['sdk_binding'], 'OpenSSL SDK changed')

    prefix = args.build / 'prefix'
    for name in LIBS:
        require(f'usr/lib/{name}' in receipt['installed'], f'OpenSSL archive missing from receipt: {name}')
    installed = {path.relative_to(prefix).as_posix(): digest(path)
                 for path in sorted(prefix.rglob('*')) if path.is_file()}
    require(installed == receipt['installed'], 'OpenSSL installed prefix changed')
    fixture = args.build / 'openssl-probe.elf'
    require(digest(fixture) == receipt['elf_sha256'] and verify_elf(fixture) == receipt['program_headers'],
            'OpenSSL ELF differs from the static build receipt')

    system_manifest = args.system / 'manifest.json'
    system, system_hash = metadata_snapshot(system_manifest)
    image = args.system / 'xos-install.iso'
    image_hash = digest(image)
    require(image_hash == system['artifacts']['xos-install.iso']['sha256'], 'system ISO changed')
    for relative, expected in system['sources'].items():
        path = (args.system_source / relative).resolve(strict=True)
        require(path.is_relative_to(args.system_source), f'system source outside checkout: {relative}')
        require(digest(path) == expected, f'system source changed: {relative}')

    report.update(build_receipt_sha256=receipt_hash, elf_sha256=receipt['elf_sha256'],
                  fixture_sha256=receipt['fixture_sha256'], sdk_binding=receipt['sdk_binding'],
                  sdk_profile_sha256=profile_hash, sdk_manifest_sha256=receipt['sdk_manifest_sha256'],
                  system_build_id=system['build_id'], system_source_sha256=system['source_sha256'],
                  system_manifest_sha256=system_hash, image_sha256=image_hash,
                  archives={name: installed[f'usr/lib/{name}'] for name in LIBS})
    return image, fixture


def run_guest(boot, disk, output_directory, case, cpu, marker, exit_code, result):
    guest = Guest(boot, case, cpu=cpu, work_disk=disk, network=False, log_dir=output_directory)
    try:
        result['qemu_version'] = subprocess.check_output(
            [guest.command[0], '--version'], text=True).splitlines()[0]
        result['cpu'] = cpu
        guest.expect(b'xos64> ', timeout=30)
        send_bytes(guest, b'run\r')
        guest.expect_supervisor(trace=True, timeout=40)
        command(guest, 'demo quiet', b'demo tasks')
        pump(guest, 1.5)
        result['resources_before'] = resources(guest)
        output = command(guest, 'exec-file /bin/openssl.elf', b'kind=', timeout=90)
        status = re.findall(rb'\[wait\] pid=\d+ kind=(\w+) code=(-?\d+)', output)
        result['exit_status'] = [(kind.decode(), int(code)) for kind, code in status]
        require(status == [(b'exited', str(exit_code).encode())], f'{case} did not exit as expected')
        lines = output.replace(b'\r', b'').splitlines()
        require(lines.count(marker) == 1, f'{case} proof marker is missing or repeated')
        require(exit_code == 0 or MARKER not in lines, f'{case} unexpectedly reported success')
        result['proof_marker'] = marker.decode()
        result['resources_after'] = resources(guest)
        require(result['resources_before'] == result['resources_after'], f'{case} guest resources changed')
    finally:
        guest.close()
        serial = output_directory / f'{case}.log'
        serial.write_bytes(guest.output)
        result['serial_sha256'] = digest(serial)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'sdk', 'profile', 'system', 'system-source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    args.system_source = args.system_source.resolve(strict=True)
    args.output.mkdir(parents=True)
    report = {'status': 'failed', 'runner_sha256': digest(Path(__file__)), 'checks': [], 'cases': {}}
    try:
        image, fixture = verify_inputs(args, report)
        with tempfile.TemporaryDirectory(prefix='xos_ssl_') as temporary:
            directory = Path(temporary)
            boot = directory / 'system.iso'
            disk = directory / 'work.img'
            exported = directory / 'roundtrip.elf'
            shutil.copyfile(image, boot)
            require(digest(boot) == report['image_sha256'], 'ISO changed during staging')
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/openssl.elf', fixture)
            transfer(disk, 'export', '/bin/openssl.elf', exported)
            require(digest(exported) == report['elf_sha256'], 'guest payload changed during staging')
            options = (('openssl_static', 'qemu64,+rdrand', MARKER, 0),
                       ('openssl_no_entropy', 'qemu64,-rdrand',
                        b'XOS glibc: invalid startup or entropy unavailable', 127))
            for name, cpu, marker, exit_code in options:
                result = report['cases'][name] = {}
                run_guest(boot, disk, args.output, name, cpu, marker, exit_code, result)
            report['checks'] = ['default_provider_sha256_abc', 'getrandom_seeded_rand_bytes',
                                'tls_1_3_p256_verified_exchange', 'tls_hostname_mismatch_rejected',
                                'missing_entropy_rejected_before_main', 'normal_exit', 'exact_resource_reclamation']
            report['status'] = 'passed'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(args.output / 'report.json')


if __name__ == '__main__':
    main()
