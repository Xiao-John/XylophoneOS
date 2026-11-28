#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify strict legacy stdio admission using real SDK-built static targets."""
import argparse
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_static_stdio_probe import INPUTS
from make_work_disk import create_fat32
from process_smoke import command, resources
from sdk_receipt import sha, tree_receipt, verify_sdk
from shell_launch_support import bind_system
from task_smoke import pump, send_bytes
from work_disk import transfer

CASES = ('raw_kernel_stdio', 'v3_keeps_descriptor_startup', 'raw_closed_stdin', 'raw_pipe_alias',
         'extra_fd_rejected', 'status_flags_rejected', 'route_mismatch_rejected', 'duplicate_fd_rejected',
         'alias_conflict_rejected', 'replacement_still_requires_v3', 'malformed_optin_rejected',
         'files_stdio_rejected', 'legacy_files_transfer_rejected', 'cleanup_record_rejected',
         'pinned_bootstrap_no_downgrade')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'system-source', 'fixture', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--repeat', type=int, choices=range(1, 9), default=3)
    args = parser.parse_args()
    system, source, fixture = (path.resolve(strict=True) for path in
                               (args.system, args.system_source, args.fixture))
    out = args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    runner_inputs = ('tests/static_stdio_compat_guest.py', 'tests/boot_smoke.py', 'tests/process_smoke.py',
                     'tests/task_smoke.py', 'tests/shell_launch_support.py', 'scripts/work_disk.py',
                     'scripts/sdk_receipt.py', 'scripts/make_work_disk.py')
    report = {'status': 'failed', 'runs': [], 'runner_sources': {name: sha(ROOT / name) for name in runner_inputs}}
    guest = None
    try:
        manifest = bind_system(system, source)
        receipt = json.loads((fixture / 'receipt.json').read_text())
        receipt_digest = sha(fixture / 'receipt.json')

        def verify():
            if bind_system(system, source) != manifest or receipt['status'] != 'built_not_run':
                raise ValueError('system or fixture binding differs')
            if receipt['sources'] != {name: sha(ROOT / name) for name in INPUTS}:
                raise ValueError('actual linked loader or fixture source changed')
            binding = verify_sdk(system / 'sdk', manifest)
            if receipt['native_sdk_binding'] != binding:
                raise ValueError('native SDK differs')
            if any(binding[key] != value for key, value in tree_receipt(fixture / 'native_sdk_snapshot').items()):
                raise ValueError('copied native SDK changed')
            if any(sha(fixture / name) != digest for name, digest in receipt['artifacts'].items()):
                raise ValueError('native target or loader fixture changed')
            if sha(fixture / 'receipt.json') != receipt_digest:
                raise ValueError('fixture receipt changed')
            if report['runner_sources'] != {name: sha(ROOT / name) for name in runner_inputs}:
                raise ValueError('runner helper changed')

        verify()
        report.update(system_build_id=manifest['build_id'], system_manifest_sha256=sha(system / 'manifest.json'),
                      image_sha256=sha(system / 'xos-install.iso'), fixture_receipt_sha256=receipt_digest,
                      loader_source_sha256=receipt['sources']['src/user/loader/load.cpp'],
                      installed_artifacts=receipt['artifacts'])
        with tempfile.TemporaryDirectory(prefix='xos_static_stdio_') as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin'); transfer(disk, 'mkdir', '/data')
            for name in receipt['artifacts']:
                transfer(disk, 'import', '/bin/' + name, fixture / name)
            preserved = out / 'preserved.txt'; preserved.write_bytes(b'unchanged\n')
            transfer(disk, 'import', '/data/preserved.txt', preserved)
            guest = Guest(system / 'xos-install.iso', 'guest', iso=True, work_disk=disk,
                          qmp_enabled=False, log_dir=out)
            report['qemu_command'] = guest.command
            guest.expect(b'xos64> ', timeout=60)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, 'demo quiet', b'demo tasks')
            command(guest, 'audio stop', b'xsh> ')
            pump(guest, 0.2)
            baseline = resources(guest)
            report['baseline'] = baseline
            for number in range(args.repeat):
                output = command(guest, 'exec-driver /bin/static_stdio_probe.elf', b'kind=exited code=', timeout=90)
                (out / ('round_' + str(number) + '.log')).write_bytes(output)
                markers = re.findall(rb'STATIC_STDIO_PASS ([a-z0-9_]+)', output)
                exits = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', output)
                if (markers != [name.encode() for name in CASES] or exits != [b'0'] or
                        output.count(b'STATIC_STDIO_OK cases=15') != 1 or b'STATIC_STDIO_FAIL' in output):
                    raise AssertionError(output[-6000:])
                actual = resources(guest)
                if actual != baseline: raise AssertionError(f'resources {actual}, expected {baseline}')
                report['runs'].append({'round': number, 'cases': list(CASES), 'native_target_executions': 4,
                                       'resources': actual, 'status': 'passed'})
            command(guest, 'sync', b'[files] sync=ok')
            guest.close(); guest = None
            readback = out / 'readback.txt'
            transfer(disk, 'export', '/data/preserved.txt', readback)
            if readback.read_bytes() != preserved.read_bytes(): raise ValueError('rejected Files transfer changed data')
            verify()
            report.update(status='passed', preserved_file_sha256=sha(readback))
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        if guest: guest.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS static stdio compatibility:', len(report['runs']) * len(CASES), 'cases')


if __name__ == '__main__':
    main()
