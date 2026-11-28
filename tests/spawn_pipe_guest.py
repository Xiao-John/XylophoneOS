#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run public glibc posix_spawn pipe/alias/EOF checks on the actual kernel."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_spawn_pipe_probe import INPUTS
from build_dynamic_program import inspect_native_sdk
from make_work_disk import create_fat32
from process_smoke import command, resources
from sdk_receipt import sha
from shell_launch_support import bind_system
from task_smoke import pump, send_bytes
from work_disk import transfer
from xypm_sdk_profile import inspect_sdk

CASES = ('routed_read_write_alias_flags_cloexec_eof_before_exit',
         'kernel_extra_alias_after_original_stdio_close',
         'independent_pipe_transfer_parent_preserved', 'closed_reader_epipe')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'system-source', 'sdk-build', 'fixture', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--repeat', type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args()
    system, source, sdk, fixture = (p.resolve(strict=True) for p in
                                    (args.system, args.system_source, args.sdk_build, args.fixture))
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'checks': [], 'rounds': args.repeat, 'inputs': {}}
    guest = None

    def bind(path, expected=None):
        actual = sha(path)
        if expected is not None and actual != expected:
            raise ValueError('input changed: ' + str(path))
        report['inputs'][str(path)] = actual

    try:
        manifest = bind_system(system, source)
        receipt = json.loads((fixture / 'receipt.json').read_bytes())
        bind(fixture / 'receipt.json')
        if receipt['status'] != 'built_not_run' or receipt['system_build_id'] != manifest['build_id']:
            raise ValueError('fixture/system identity differs')
        for name in INPUTS:
            bind(ROOT / name, receipt['sources'][name])
        for name in ('tests/spawn_pipe_guest.py', 'tests/boot_smoke.py', 'tests/process_smoke.py',
                     'tests/task_smoke.py', 'tests/shell_launch_support.py', 'scripts/make_work_disk.py',
                     'scripts/work_disk.py', 'scripts/run_qemu.py'):
            bind(ROOT / name)
        for name, expected in receipt['snapshot_hashes'].items():
            bind(fixture / name, expected)
        for name, expected in receipt['artifacts'].items():
            bind(fixture / name, expected)
        bind(system / 'manifest.json', receipt['system_manifest_sha256'])
        bind(system / 'xos-install.iso')

        def verify():
            for name, expected in list(report['inputs'].items()):
                if sha(Path(name)) != expected:
                    raise ValueError('bound input changed: ' + name)
            if (bind_system(system, source) != manifest or
                    inspect_sdk('glibc', sdk)['binding'] != receipt['sdk_binding'] or
                    inspect_native_sdk(system / 'sdk') != receipt['native_sdk_binding']):
                raise ValueError('native system or SDK changed')

        verify()
        disk = out / 'work.img'
        create_fat32(disk, 512)
        transfer(disk, 'mkdir', '/tests'); transfer(disk, 'mkdir', '/data')
        transfer(disk, 'import', '/tests/spawn_pipe.elf', fixture / 'spawn_pipe.elf')
        guest = Guest(system / 'xos-install.iso', 'serial', iso=True, work_disk=disk,
                      qmp_enabled=False, log_dir=out)
        report.update(system_build_id=manifest['build_id'], qemu_command=guest.command,
                      scope=receipt['scope'], loader_mode=receipt.get('loader_mode', 'diagnostic_override'),
                      loader_sha256=receipt['sources']['src/user/loader/load.cpp'])
        guest.expect(b'xos64> ', timeout=60)
        send_bytes(guest, b'run\r'); guest.expect_supervisor(trace=True, timeout=60)
        command(guest, 'demo quiet', b'demo tasks')
        command(guest, 'audio stop', b'xsh> ')
        pump(guest, 0.2)
        baseline = resources(guest)
        report['baseline'] = baseline
        for number in range(args.repeat):
            output = command(guest, 'exec-driver /tests/spawn_pipe.elf', b'kind=exited code=', timeout=45)
            (out / ('round_' + str(number) + '.log')).write_bytes(output)
            actual = resources(guest)
            markers = re.findall(rb'SPAWN_PIPE_PASS ([a-z0-9_]+)', output)
            exits = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', output)
            if (markers != [name.encode() for name in CASES] or exits != [b'0'] or
                    output.count(b'SPAWN_PIPE_OK cases=4') != 1 or b'SPAWN_PIPE_FAIL' in output or actual != baseline):
                raise AssertionError({'output': output[-6000:].decode(errors='replace'), 'resources': actual})
            report['checks'].append({'round': number, 'status': 'passed', 'cases': list(CASES),
                                     'child_executions': 5, 'resources': actual})
        guest.close(); guest = None
        verify()
        report.update(status='passed', input_count=len(report['inputs']))
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        if guest: guest.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
