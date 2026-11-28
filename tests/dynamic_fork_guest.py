#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify dynamic fork controller migration against the exact public GNU C closure."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_dynamic_program import inspect_native_sdk
from make_work_disk import create_fat32
from process_smoke import command, resources
from sdk_receipt import verify_sdk
from shell_launch_support import bind_system, check_hash, relative_file, sha
from task_smoke import send_bytes, pump
from work_disk import transfer
from xypm_sdk_profile import inspect_sdk, verify_profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'system-source', 'runtime-build', 'runtime-source',
                 'launcher-build', 'launcher-source',
                 'dash-receipt', 'dash-source', 'dash-sdk', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--stage', type=Path, action='append', required=True)
    parser.add_argument('--rounds', type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.rounds <= 3:
        parser.error('rounds must be between one and three')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'scope': 'P1-K2 public GNU C fork/controller migration; no C++ or terminal-actor claim',
              'rounds': args.rounds, 'checks': [], 'inputs': {}, 'installed': {}}
    inputs = report['inputs']
    guest = None
    disk = out / 'work.img'

    def bind(path, expected=None):
        path = Path(path).resolve(strict=True)
        actual = sha(path)
        if expected is not None and actual != expected:
            raise ValueError('input digest mismatch: ' + str(path))
        if str(path) in inputs and inputs[str(path)] != actual:
            raise ValueError('input changed during binding: ' + str(path))
        inputs[str(path)] = actual
        return actual

    def read(path):
        bind(path)
        return json.loads(Path(path).read_bytes())

    def payload(path, source, expected):
        if (not path.startswith('/') or re.fullmatch(r'/[A-Za-z0-9_./+\-]+', path) is None
                or any(part in ('', '.', '..') for part in path[1:].split('/'))):
            raise ValueError('noncanonical guest payload path: ' + path)
        bind(source, expected)
        if path in report['installed'] and report['installed'][path] != expected:
            raise ValueError('conflicting bytes at shared guest path: ' + path)
        report['installed'][path] = expected
        files[path] = Path(source)

    def verify_all():
        for path, expected in inputs.items():
            check_hash(Path(path), expected, 'bound guest input')
        if bind_system(args.system, args.system_source) != system:
            raise ValueError('system changed during guest qualification')
        if inspect_native_sdk(args.system / 'sdk') != native_binding:
            raise ValueError('native SDK changed during guest qualification')
        if inspect_sdk('glibc', args.runtime_build / 'sdk_snapshot')['binding'] != c_binding:
            raise ValueError('C SDK snapshot changed during guest qualification')
        if verify_profile(json.loads((args.dash_sdk.parent / 'profile.json').read_bytes()),
                          'glibc', args.dash_sdk) != dash_binding:
            raise ValueError('outer dash SDK changed during guest qualification')

    try:
        for relative in ('tests/dynamic_fork_guest.py', 'tests/boot_smoke.py',
                         'tests/process_smoke.py', 'tests/task_smoke.py', 'tests/shell_launch_support.py',
                         'scripts/make_work_disk.py', 'scripts/work_disk.py', 'scripts/run_qemu.py',
                         'scripts/build_dynamic_program.py', 'scripts/xypm_sdk_profile.py'):
            bind(ROOT / relative)
        system = bind_system(args.system, args.system_source)
        bind(args.system / 'manifest.json')
        native_binding = inspect_native_sdk(args.system / 'sdk')
        native_receipt = verify_sdk(args.system / 'sdk', system)
        runtime = read(args.runtime_build / 'manifest.json')
        if runtime.get('status') != 'public_runtime_built_not_run' or not runtime.get('public_startup'):
            raise ValueError('public GNU startup build is required')
        for group in ('recipe_inputs', 'port_inputs', 'native_inputs'):
            for name, expected in runtime[group].items():
                bind(relative_file(args.runtime_source, name), expected)
        for name, expected in runtime['artifacts'].items():
            bind(relative_file(args.runtime_build, name), expected)
        c_binding = inspect_sdk('glibc', args.runtime_build / 'sdk_snapshot')['binding']
        if c_binding != runtime['sdk_binding']:
            raise ValueError('public runtime C SDK binding differs')
        if (c_binding['sdk_manifest_sha256'] != runtime['expected_sdk_manifest_sha256']
                or c_binding['sdk_tree_sha256'] != runtime['expected_sdk_tree_sha256']):
            raise ValueError('runtime does not retain both independently supplied SDK anchors')

        launcher = read(args.launcher_build / 'receipt.json')
        if (launcher.get('status') != 'built_not_run' or launcher['c_sdk_binding'] != c_binding
                or launcher['native_sdk_binding'] != native_receipt
                or launcher['native_system_build_id'] != system['build_id']):
            raise ValueError('launcher SDK composition differs from runtime/system')
        bind(args.system / 'manifest.json', launcher['native_system_manifest_sha256'])
        for name, expected in launcher['sources'].items():
            bind(relative_file(args.launcher_source, name), expected)
        for name, expected in launcher['artifacts'].items():
            bind(relative_file(args.launcher_build, name), expected)
        if inspect_sdk('glibc', args.launcher_build / 'sdk_snapshot')['binding'] != c_binding:
            raise ValueError('launcher independent complete C SDK snapshot differs')
        if verify_sdk(args.launcher_build / 'native_sdk_snapshot', system) != native_receipt:
            raise ValueError('launcher complete native SDK snapshot differs')

        files, stages, slots = {}, {}, {}
        report['generation_startup_budgets_ns'] = {}
        for stage_path in args.stage:
            stage = read(stage_path / 'manifest.json')
            if (stage.get('status') != 'built_not_run' or not stage.get('public_startup')
                    or stage['native_abi'] != runtime['native_abi'] or stage['sdk_binding'] != c_binding
                    or stage['native_sdk_binding'] != native_binding):
                raise ValueError('program stage belongs to another public composition')
            for path, expected in stage['inputs'].items():
                bind(path, expected)
            if inspect_native_sdk(stage_path / 'native_sdk_snapshot') != native_binding:
                raise ValueError('program native SDK snapshot differs')
            generation = stage['generation']
            matches = [(i, root) for i, root in enumerate(launcher['approved_generations'])
                       if root['id'] == generation['id'] and root['sha256'] == generation['sha256']
                       and root['manifest'] == generation['guest']]
            if len(matches) != 1:
                raise ValueError('program generation is not explicitly approved by this launcher')
            slot, approved = matches[0]
            if stage['name'] in stages:
                raise ValueError('duplicate program stage')
            stages[stage['name']], slots[stage['name']] = stage, slot
            for path, item in stage['files'].items():
                payload(path, relative_file(stage_path, item['local']), item['sha256'])
            generation_path = relative_file(stage_path, generation['local'])
            payload(generation['guest'], generation_path, generation['sha256'])
            generation_bytes = generation_path.read_bytes()
            if (len(generation_bytes) < 128 or struct.unpack_from('<QI', generation_bytes) != (0x314e4547534f5858, 1)
                    or struct.unpack_from('<Q', generation_bytes, 112)[0] != 30_000_000_000):
                raise ValueError('the fixture must retain the existing version-1 thirty-second startup budget')
            report['generation_startup_budgets_ns'][stage['name']] = 30_000_000_000
            bind(args.launcher_build / approved['snapshot'], generation['sha256'])
        if set(stages) != {'k2fork', 'k5pipes'}:
            raise ValueError('the independently approved k2fork and k5pipes C stages are required')
        payload('/usr/bin/dynamic-run', args.launcher_build / 'dynamic-run.elf',
                launcher['artifacts']['dynamic-run.elf'])

        dash = read(args.dash_receipt)
        dash_profile = read(args.dash_sdk.parent / 'profile.json')
        dash_binding = verify_profile(dash_profile, 'glibc', args.dash_sdk)
        if dash['sdk_profile_binding'] != dash_binding:
            raise ValueError('outer dash SDK differs from its build receipt')
        for name, expected in dash['inputs'].items():
            if name == 'profile':
                if expected != dash_binding['profile_sha256']:
                    raise ValueError('outer dash profile digest differs')
                continue
            if name == 'sdk/manifest.json':
                bind(args.dash_sdk / 'manifest.json', expected)
                continue
            base, relative = (args.dash_sdk / 'sysroot', name[4:]) if name.startswith('sdk/') else (args.dash_source, name)
            bind(relative_file(base, relative), expected)
        payload('/usr/bin/dash', relative_file(args.dash_source, dash['elf']), dash['sha256'])
        report['outer_dash_scope'] = 'ordinary shell entry only; its static libc is separately bound and is not the tested public libc'
        report['native_build_id'] = system['build_id']
        report['native_sdk_binding'] = native_binding
        report['c_sdk_binding'] = c_binding
        report['native_abi'] = runtime['native_abi']

        input_file = out / 'input.txt'
        input_file.write_bytes(b'ABCDEFGH\n')
        payload('/tests/input', input_file, sha(input_file))
        definitions = []
        markers = {
            'fork-exec': ('DYNAMIC_FORK_PASS failed_exec_retains_control_pid_fds',
                          'DYNAMIC_FORK_PASS child_exec_pid_fd_alias_cloexec_pipe',
                          'DYNAMIC_FORK_PASS parent_wait_owner_and_resources'),
            'nested': ('DYNAMIC_FORK_PASS nested_same_pid_exec', 'DYNAMIC_FORK_PASS nested_controller_chain'),
            'authority': ('DYNAMIC_FORK_PASS denied_fork_same_pid_exec_no_authority_gain',),
            'threads': ('DYNAMIC_FORK_PASS thread_profile_rejected',),
            'owner-exit': ('DYNAMIC_FORK_PASS controller_child_adopted_before_exit',
                           'DYNAMIC_FORK_PASS controller_normal_exit',
                           'DYNAMIC_FORK_PASS dead_controller_denies_without_fd_or_pid_loss')}
        for mode, expected in markers.items():
            line = 'dynamic-run ' + ('--without-create ' if mode == 'authority' else '')
            line += str(slots['k2fork']) + ' /apps/k2fork/main ' + mode
            definitions.append((mode + '-xsh', line, expected))
            script = out / (mode + '.sh')
            script.write_text('/usr/bin/' + line + '\n')
            payload('/tests/' + mode + '.sh', script, sha(script))
            definitions.append((mode + '-dash', 'dash /tests/' + mode + '.sh', expected))
        pipe_markers = (
            'INDEPENDENT_PIPE_PASS independent_alias_flags_cloexec_eof_before_exit',
            'INDEPENDENT_PIPE_PASS same_pid_exec',
            'INDEPENDENT_PIPE_PASS failed_and_successful_exec_parent_preserved',
            'INDEPENDENT_PIPE_PASS independent_reader_close_epipe',
            'INDEPENDENT_PIPE_PASS eight_objects_sixteen_references_thirtytwo_descriptors',
            'INDEPENDENT_PIPE_OK cases=4')
        line = 'dynamic-run ' + str(slots['k5pipes']) + ' /apps/k5pipes/main'
        definitions.append(('independent-pipes-xsh', line, pipe_markers))
        script = out / 'independent_pipes.sh'; script.write_text('/usr/bin/' + line + '\n')
        payload('/tests/independent_pipes.sh', script, sha(script))
        definitions.append(('independent-pipes-dash', 'dash /tests/independent_pipes.sh', pipe_markers))
        data_seed = out / 'data_seed.txt'; data_seed.write_text('pipe lifecycle gate directory\n')
        payload('/data/seed', data_seed, sha(data_seed))
        create_fat32(disk, 512)
        parents = sorted({str(parent) for path in files for parent in Path(path).parents if str(parent) != '/'},
                         key=lambda path: (path.count('/'), path))
        for path in parents:
            transfer(disk, 'mkdir', path)
        for path, source in files.items():
            transfer(disk, 'import', path, source)
        verify_all()
        report['work_disk_before_sha256'] = sha(disk)
        guest = Guest(args.system / 'xos-install.iso', 'dynamic_fork', work_disk=disk,
                      iso=True, qmp_enabled=False, log_dir=out)
        report['qemu_command'] = guest.command
        report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
        bind(guest.command[0])
        guest.expect(b'xos64> ', timeout=40)
        send_bytes(guest, b'run\r')
        guest.expect_supervisor(trace=True, timeout=40)
        command(guest, 'demo quiet', b'demo tasks ')
        command(guest, 'audio stop', b'xsh> ')
        pump(guest, 0.2)
        report['baseline_resources'] = resources(guest)
        for round_index in range(args.rounds):
            for name, line, markers in definitions:
                before = resources(guest)
                started = time.monotonic()
                row = {'name': name, 'round': round_index + 1, 'command': line, 'status': 'failed',
                       'resources_before': before}
                report['checks'].append(row)
                began = len(guest.output)
                output = command(guest, line, b'xsh> ', timeout=240)
                if name.startswith('owner-exit'):
                    guest.expect(b'DYNAMIC_FORK_PASS dead_controller_denies_without_fd_or_pid_loss', start=began, timeout=30)
                    pump(guest, 0.2)
                    output = bytes(guest.output)[began:]
                row['seconds'] = round(time.monotonic() - started, 3)
                row['output'] = output.decode(errors='replace')
                # The owner may exit and return the shell prompt before its
                # orphan prints its final result.  Accept that exact prompt
                # prefix once; still require a complete, otherwise exact line.
                lines = [line.removeprefix(b'xsh> ') if name.startswith('owner-exit') else line
                         for line in output.splitlines()]
                if any(marker.encode() not in lines for marker in markers):
                    raise AssertionError(name + ' missing complete program result line: ' + repr(output[-4000:]))
                completed = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)(?:\r?\n|$)', output)
                if not completed or int(completed[-1]) != 0:
                    raise AssertionError(name + ' missing successful final completion: ' + repr(output[-4000:]))
                if not re.search(rb'DYNAMIC_RUN_EXIT slot=\d+ generation=\d+ pid=\d+ outcome=1 code=0\r?\n', output):
                    raise AssertionError(name + ' missing successful public-controller completion')
                pump(guest, 0.2)
                after = resources(guest)
                row['resources_after'] = after
                if before != after or after != report['baseline_resources']:
                    raise AssertionError(name + ' did not exactly reclaim pages/process/completion resources')
                row['status'] = 'passed'
                (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
                print('PASS', name, 'round', round_index + 1, 'seconds', row['seconds'], flush=True)
        began = len(guest.output)
        line = 'dynamic-run ' + str(slots['k2fork']) + ' /apps/k2fork/main owner-kill'
        send_bytes(guest, line.encode() + b'\r')
        guest.expect(b'DYNAMIC_FORK_KILL_READY parent=', start=began, timeout=120)
        send_bytes(guest, b'\x1b')
        guest.expect(b'event=cancelled_by_escape', start=began, timeout=30)
        guest.expect(b'kind=killed code=-27', start=began, timeout=30)
        guest.expect(b'xsh> ', start=began, timeout=30)
        pump(guest, 0.2)
        after = resources(guest)
        if after != report['baseline_resources']:
            raise AssertionError('killed controller/descendants did not reclaim every resource')
        report['checks'].append({'name': 'owner-kill-xsh', 'status': 'passed', 'resources_after': after,
                                 'output': bytes(guest.output)[began:].decode(errors='replace')})
        verify_all()
        report['status'] = 'passed'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        if guest:
            guest.close()
        if disk.exists():
            report['work_disk_after_sha256'] = sha(disk)
            disk.unlink()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        evidence = {str(path.relative_to(out)): sha(path) for path in sorted(out.rglob('*'))
                    if path.is_file() and path.name != 'evidence_manifest.json'}
        (out / 'evidence_manifest.json').write_text(json.dumps({'status': report['status'], 'files': evidence}, indent=2) + '\n')


if __name__ == '__main__':
    main()
