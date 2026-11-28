#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify the independent terminal actor and dynamic controller composition."""
import argparse
import json
from pathlib import Path
import re
import secrets
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_dynamic_program import inspect_native_sdk
from build_dynamic_terminal_supervisor import bind_supervisor, verify_native_payload
from make_work_disk import create_fat32
from sdk_receipt import verify_sdk
from shell_launch_support import bind_system, relative_file, sha
from task_smoke import send_bytes, pump
from terminal_resource_snapshot import bind_kernel_resources, sample_kernel_resources, verify_kernel_resource_pair
from work_disk import transfer
from xypm_sdk_profile import inspect_sdk

OWNER_SETUP_FIELDS = ('control', 'owner', 'actor', 'controller', 'child', 'baseline_pages',
    'baseline_tasks', 'baseline_completions', 'before_pages', 'before_tasks', 'before_completions',
    'owner_user_pages', 'owner_kernel_stack_pages', 'owner_channels', 'owner_pipe_references',
    'pending_seen_ns', 'exit_started_ns')
OWNER_EVENT_FIELDS = ('kind', 'pid', 'parent', 'owner', 'actor', 'child', 'started_ns', 'finished_ns',
    'generation', 'threads', 'blocked', 'state', 'terminal_send', 'terminal_receive', 'ready', 'ack',
    'read_result', 'read_errno', 'exec_result', 'exec_errno', 'raw_send', 'raw_receive', 'file_byte',
    'pipe_result', 'controller_preserved', 'authority', 'wait_status')
OWNER_FINAL_FIELDS = ('observer_pid', 'observer_parent', 'free_pages', 'tasks', 'observer_thread_results',
    'observer_user_pages', 'observer_kernel_stack_pages', 'observer_channels', 'observer_pipe_references',
    'stable_ns', 'failure_line', 'failure_code', 'process_stats_query_result', 'thread_stats_query_result',
    'observer_threads', 'observer_reserved_threads', 'observer_waiting_threads')


def owner_receipt(data, nonce, control):
    if len(data) != 1224 or struct.unpack_from('<4Q', data) != (0x3152454e574f5458, 2, 1224, 1):
        raise AssertionError('owner observer did not persist a complete successful receipt: ' + data[:64].hex())
    if data[32:64] != nonce:
        raise AssertionError('owner observer receipt belongs to another run nonce')
    def fields(names, offset):
        raw = struct.unpack_from('<32Q', data, offset)
        if any(raw[len(names):]): raise AssertionError('owner evidence has nonzero reserved fields')
        return dict(zip(names, raw))
    setup = fields(OWNER_SETUP_FIELDS, 64)
    events = [fields(OWNER_EVENT_FIELDS, 320 + i * 256) for i in range(3)]
    final = dict(zip(OWNER_FINAL_FIELDS, struct.unpack_from('<17Q', data, 1088)))
    if (setup['control'] != int(control) or setup['owner'] == final['observer_pid'] or not setup['owner']
            or not final['observer_pid'] or final['observer_parent'] != 0 or final['tasks'] != 2
            or final['observer_thread_results'] != 0 or final['observer_pipe_references'] != 0
            or final['observer_channels'] != 0 or final['observer_threads'] != 1
            or final['observer_reserved_threads'] != 0 or final['observer_waiting_threads'] != 0
            or final['process_stats_query_result'] != (1 << 64) - 1 or final['thread_stats_query_result'] != 0
            or final['stable_ns'] < 250_000_000 or final['failure_line'] or final['failure_code']
            or not final['observer_user_pages'] or final['observer_kernel_stack_pages'] != 1
            or not setup['owner_user_pages'] or setup['owner_kernel_stack_pages'] != 1
            or setup['baseline_tasks'] != 3 or setup['baseline_completions'] != 1
            or setup['owner_pipe_references'] != 1):
        raise AssertionError('owner death/final resource evidence differs: ' + repr((setup, final)))
    if control:
        if any(setup[key] for key in ('actor', 'controller', 'child', 'pending_seen_ns')) or any(any(event.values()) for event in events):
            raise AssertionError('calibration unexpectedly contains an actor/controller case')
    else:
        pending, child, parent = events
        if len({setup[key] for key in ('owner', 'actor', 'controller', 'child')} | {final['observer_pid']}) != 5:
            raise AssertionError('owner, actor, controller, child and observer are not distinct')
        if (pending['kind'] != 1 or pending['pid'] != setup['controller'] or pending['child'] != setup['child']
                or pending['owner'] != setup['owner'] or pending['actor'] != setup['actor']
                or pending['state'] != 5 or pending['threads'] != 1 or pending['blocked'] != 1
                or pending['generation'] != 1
                or not child['started_ns'] <= pending['started_ns'] <= pending['finished_ns'] <=
                    setup['pending_seen_ns'] <= setup['exit_started_ns'] <= child['finished_ns']
                or child['finished_ns'] - child['started_ns'] >= 10_000_000_000):
            raise AssertionError('read was not proved pending before the actual owner exit: ' + repr(events))
        negative_one = (1 << 64) - 1
        if (child['kind'] != 2 or child['pid'] != setup['child'] or child['parent'] != setup['controller']
                or child['owner'] != setup['owner'] or child['actor'] != setup['actor']
                or child['read_result'] != negative_one or child['read_errno'] != 32
                or child['exec_result'] != negative_one or child['exec_errno'] != 5
                or child['raw_send'] != negative_one or child['raw_receive'] != negative_one
                or child['file_byte'] != ord('A') or child['pipe_result'] != 0
                or child['controller_preserved'] != 1 or child['authority'] != 1
                or any(not child[key] for key in ('terminal_send', 'terminal_receive', 'ready', 'ack'))
                or len({child[key] for key in ('terminal_send', 'terminal_receive', 'ready', 'ack')}) != 4
                or parent['kind'] != 3 or parent['pid'] != setup['controller'] or parent['child'] != setup['child']
                or parent['owner'] != setup['owner'] or parent['actor'] != setup['actor']
                or parent['file_byte'] != ord('B') or parent['wait_status'] != 0):
            raise AssertionError('owner-death stale sessions/PID/FD/controller evidence differs: ' + repr(events))
    return {'nonce': nonce.hex(), 'setup': setup, 'events': events, 'final': final,
            'net_pages_returned_from_pre_actor_owner_observer_state': final['free_pages'] - setup['baseline_pages']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base-system', 'system', 'runtime-build', 'launcher-build', 'supervisor-build', 'stage', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    disk = out / 'work.img'
    report = {'status': 'failed', 'scope': 'real COM1 actor plus independent public GNU launch controller',
              'rounds': 2, 'checks': [], 'inputs': {}, 'installed': {}}
    inputs, files = report['inputs'], {}
    guest = None

    def bind(path, expected=None):
        path = Path(path).resolve(strict=True)
        value = sha(path)
        if expected is not None and value != expected:
            raise ValueError('input digest differs: ' + str(path))
        if str(path) in inputs and inputs[str(path)] != value:
            raise ValueError('input changed: ' + str(path))
        inputs[str(path)] = value
        return value

    def read(path):
        bind(path)
        return json.loads(Path(path).read_bytes())

    def payload(path, local, expected):
        if (re.fullmatch(r'/[A-Za-z0-9_./+\-]+', path) is None or path.endswith('/') or
                any(part in ('', '.', '..') for part in path[1:].split('/'))):
            raise ValueError('noncanonical guest payload path')
        bind(local, expected)
        if path in files and report['installed'][path] != expected:
            raise ValueError('conflicting payload bytes')
        files[path] = Path(local)
        report['installed'][path] = expected

    def verify_all():
        for path, expected in inputs.items():
            if sha(Path(path)) != expected:
                raise ValueError('bound input changed: ' + path)
        if bind_system(args.base_system, ROOT) != base or bind_system(args.system, ROOT) != system:
            raise ValueError('a bound system changed')
        if inspect_native_sdk(args.base_system / 'sdk') != base_native or inspect_native_sdk(args.system / 'sdk') != final_native:
            raise ValueError('a complete native SDK changed')
        if inspect_sdk('glibc', args.runtime_build / 'sdk_snapshot')['binding'] != c_binding:
            raise ValueError('the complete C SDK changed')
        if bind_supervisor(args.supervisor_build, ROOT)[1] != supervisor_binding:
            raise ValueError('the explicit supervisor producer changed')
        verify_native_payload(supervisor, args.system / 'sdk')

    try:
        for name in ('tests/dynamic_terminal_guest.py', 'tests/boot_smoke.py', 'tests/task_smoke.py',
                     'tests/terminal_resource_snapshot.py',
                     'tests/shell_launch_support.py', 'scripts/build_dynamic_terminal_supervisor.py',
                     'scripts/build_dynamic_program.py', 'scripts/xypm_sdk_profile.py', 'scripts/sdk_receipt.py',
                     'scripts/make_work_disk.py', 'scripts/work_disk.py', 'scripts/run_qemu.py',
                     'tests/fixtures/dynamic_terminal_owner_probe.hpp',
                     'tests/fixtures/public_runtime/terminal_owner_evidence.h'):
            bind(ROOT / name)
        base, system = (bind_system(path, ROOT) for path in (args.base_system, args.system))
        kernel_resources = bind_kernel_resources(args.system, ROOT, out / 'kernel_resource_binding')
        report['kernel_resource_binding'] = kernel_resources
        for name, expected in kernel_resources['inputs'].items(): bind(name, expected)
        for path in (args.base_system, args.system): bind(path / 'manifest.json')
        base_native, final_native = (inspect_native_sdk(path / 'sdk') for path in (args.base_system, args.system))
        base_receipt = verify_sdk(args.base_system / 'sdk', base)
        verify_sdk(args.system / 'sdk', system)
        binary, supervisor_binding, supervisor = bind_supervisor(args.supervisor_build, ROOT)
        bind(args.supervisor_build / 'receipt.json')
        for name, expected in supervisor['inputs'].items(): bind(relative_file(ROOT, name), expected)
        for name, expected in supervisor['artifacts'].items(): bind(relative_file(args.supervisor_build, name), expected)
        if system.get('dynamic_terminal_probe') != supervisor_binding:
            raise ValueError('system does not embed this exact explicit supervisor binding')
        bind(args.system / 'user_supervisor.elf', sha(binary))
        verify_native_payload(supervisor, args.system / 'sdk')
        if (base['build_id'] == system['build_id'] or base_native == final_native or
                supervisor_binding['base_system_manifest_sha256'] != sha(args.base_system / 'manifest.json')):
            raise ValueError('producer and test system must retain distinct complete identities')
        runtime = read(args.runtime_build / 'manifest.json')
        if runtime.get('status') != 'public_runtime_built_not_run' or not runtime.get('public_startup'):
            raise ValueError('matching public GNU runtime is required')
        for group in ('recipe_inputs', 'port_inputs', 'native_inputs'):
            for name, expected in runtime[group].items(): bind(relative_file(ROOT, name), expected)
        for name, expected in runtime['artifacts'].items(): bind(relative_file(args.runtime_build, name), expected)
        c_binding = inspect_sdk('glibc', args.runtime_build / 'sdk_snapshot')['binding']
        if (c_binding != runtime['sdk_binding'] or c_binding['sdk_manifest_sha256'] != runtime['expected_sdk_manifest_sha256']
                or c_binding['sdk_tree_sha256'] != runtime['expected_sdk_tree_sha256']):
            raise ValueError('complete C SDK does not match both independent anchors')
        launcher = read(args.launcher_build / 'receipt.json')
        if (launcher.get('status') != 'built_not_run' or launcher['native_sdk_binding'] != base_receipt
                or launcher['native_system_build_id'] != base['build_id'] or launcher['c_sdk_binding'] != c_binding
                or launcher['sdk_manifest_sha256'] != c_binding['sdk_manifest_sha256']
                or launcher['sdk_tree_sha256'] != c_binding['sdk_tree_sha256']
                or len(launcher['approved_generations']) != 1):
            raise ValueError('approved controller belongs to another composition')
        for name, expected in launcher['sources'].items(): bind(relative_file(ROOT, name), expected)
        for name, expected in launcher['artifacts'].items(): bind(relative_file(args.launcher_build, name), expected)
        if (verify_sdk(args.launcher_build / 'native_sdk_snapshot', base) != base_receipt or
                inspect_sdk('glibc', args.launcher_build / 'sdk_snapshot')['binding'] != c_binding):
            raise ValueError('controller SDK snapshots differ')
        stage = read(args.stage / 'manifest.json')
        if (stage.get('status') != 'built_not_run' or stage['name'] != 'k2terminal' or not stage.get('public_startup')
                or stage['native_abi'] != runtime['native_abi'] or stage['sdk_binding'] != c_binding
                or stage['native_sdk_binding'] != base_native
                or inspect_native_sdk(args.stage / 'native_sdk_snapshot') != base_native):
            raise ValueError('terminal C generation differs from the exact producer composition')
        for name, expected in stage['inputs'].items(): bind(name, expected)
        generation, approved = stage['generation'], launcher['approved_generations'][0]
        if (generation['id'] != approved['id'] or generation['sha256'] != approved['sha256']
                or generation['guest'] != approved['manifest'] or supervisor['approved_generation'] != approved):
            raise ValueError('terminal C generation is not the explicitly approved root')
        bind(args.launcher_build / approved['snapshot'], generation['sha256'])
        for path, item in stage['files'].items(): payload(path, relative_file(args.stage, item['local']), item['sha256'])
        payload(generation['guest'], relative_file(args.stage, generation['local']), generation['sha256'])
        generation_bytes = relative_file(args.stage, generation['local']).read_bytes()
        if (len(generation_bytes) < 128 or struct.unpack_from('<QI', generation_bytes) != (0x314e4547534f5858, 1)
                or struct.unpack_from('<Q', generation_bytes, 112)[0] != 30_000_000_000):
            raise ValueError('terminal fixture requires the existing version-1 thirty-second startup budget')
        report['generation_startup_budget_ns'] = 30_000_000_000
        report['positive_packet_wait_budget_ns'] = 65_000_000_000
        actor = args.system / 'user_terminal.image.elf'
        payload('/bin/terminal.elf', actor, system['artifacts'][actor.name]['sha256'])
        payload('/usr/bin/terminal-supervisor', binary, sha(binary))
        data = out / 'terminal_input.txt'
        data.write_bytes(b'ABCDEFGH\n')
        payload('/tests/terminal_input', data, sha(data))
        report.update(base_system_build_id=base['build_id'], system_build_id=system['build_id'],
            base_native_sdk_binding=base_native, test_native_sdk_binding=final_native,
            exact_native_compilation_payload_sha256=supervisor['native_payload_sha256'],
            c_sdk_binding=c_binding, native_abi=runtime['native_abi'], supervisor_binding=supervisor_binding)
        create_fat32(disk, 512)
        parents = sorted({str(parent) for path in files for parent in Path(path).parents if str(parent) != '/'},
                         key=lambda path: (path.count('/'), path))
        for path in parents: transfer(disk, 'mkdir', path)
        for path, source in files.items(): transfer(disk, 'import', path, source)
        verify_all()
        report['work_disk_before_sha256'] = sha(disk)
        guest = Guest(args.system / 'xos-install.iso', 'dynamic_terminal', work_disk=disk,
                      iso=True, qmp_enabled=False, log_dir=out)
        report['qemu_command'] = guest.command
        report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
        bind(guest.command[0])
        guest.expect(b'xos64> ', timeout=40)
        send_bytes(guest, b'run\r')
        guest.expect(b'DYNAMIC_TERMINAL_BOOT_READY', timeout=40)
        send_bytes(guest, b'!')
        limits_marker = b'DYNAMIC_TERMINAL_CHANNEL_LIMITS_PASS\n'
        guest.expect(limits_marker, timeout=60)
        cursor = bytes(guest.output).index(limits_marker) + len(limits_marker)
        report['checks'].append({'name': 'native_channel_limits_and_ownership', 'status': 'passed'})
        for round_index in range(2):
            for name in ('direct', 'fork', 'authority', 'owner-exit', 'owner-kill', 'actor-death'):
                began = cursor
                started = time.monotonic()
                row = {'name': name, 'round': round_index + 1, 'status': 'failed'}
                report['checks'].append(row)
                if name in ('direct', 'fork', 'authority'):
                    guest.expect(('DYNAMIC_TERMINAL_INPUT_READY ' + name + '\n').encode(), start=began, timeout=90)
                    send_bytes(guest, b'T')
                marker = ('DYNAMIC_TERMINAL_CASE_PASS ' + name + ' resources=').encode()
                guest.expect(marker, start=began, timeout=90)
                guest.expect(b'\n', start=bytes(guest.output).index(marker, began) + len(marker), timeout=10)
                output = bytes(guest.output)[began:]
                match = re.search(re.escape(marker) + rb'(\d+),(\d+),(\d+)\r?\n', output)
                if match is None:
                    raise AssertionError('missing complete case/resource result: ' + repr(output[-2000:]))
                cursor = began + match.end()
                output = bytes(guest.output)[began:cursor]
                if b'DYNAMIC_TERMINAL_FAIL ' in output or b'DYNAMIC_TERMINAL_SUPERVISOR_FAIL ' in output:
                    raise AssertionError('terminal fixture reported a failure: ' + repr(output[-2000:]))
                current = [int(value) for value in match.groups()]
                if 'baseline_resources' not in report: report['baseline_resources'] = current
                if current != report['baseline_resources']:
                    raise AssertionError('terminal cases did not retain one exact resource baseline')
                if name in ('direct', 'fork', 'authority'):
                    timing = re.search(rb'DYNAMIC_TERMINAL_NEW_MAIN ' + name.encode()
                        + rb' pid=(\d+) failed_exec_ns=(\d+) exec_ns=(\d+)\r?\n', output)
                    completion = re.search(rb'DYNAMIC_TERMINAL_COMPLETION_TIMING ' + name.encode()
                        + rb' packet_wait_ns=(\d+)\r?\n', output)
                    if timing is None or completion is None:
                        raise AssertionError('missing explicit new-main or completion timing observation')
                    if int(timing[2]) >= 30_000_000_000 or int(timing[3]) >= 30_000_000_000:
                        raise AssertionError('observed exec exceeds the fixture generation startup budget')
                    if int(completion[1]) >= 65_000_000_000:
                        raise AssertionError('positive completion exceeded its aggregate fixture budget')
                    row['timing_ns'] = {'failed_exec': int(timing[2]), 'successful_exec_to_main': int(timing[3]),
                                        'supervisor_packet_wait': int(completion[1])}
                    if not re.search(rb'DYNAMIC_TERMINAL_PASS ' + name.encode() + rb' pid=\d+\r?\n', output):
                        raise AssertionError('application did not report successful same-PID exec')
                    if ('DYNAMIC_TERMINAL_FAILED_EXEC_PRESERVED ' + name + '\n').encode() not in output:
                        raise AssertionError('failed exec preservation did not run')
                if name == 'fork' and b'DYNAMIC_TERMINAL_FORK_PARENT_PRESERVED\n' not in output:
                    raise AssertionError('fork parent/controller preservation did not run')
                if name == 'owner-exit' and b'DYNAMIC_TERMINAL_CONTROLLER_EXIT_CLOSED_FOREGROUND_PASS\n' not in output:
                    raise AssertionError('controller-exit foreground revocation and survivor PID/FD checks did not run')
                row.update(status='passed', seconds=round(time.monotonic() - started, 3),
                           resources=current, output=output.decode(errors='replace'))
                (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
                print('PASS terminal', name, 'round', round_index + 1, flush=True)
        guest.expect(b'DYNAMIC_TERMINAL_BUDGET_QUOTA_PASS\n', start=cursor, timeout=30)
        guest.expect(b'DYNAMIC_TERMINAL_START_ROLLBACK_PASS actor_channels=2\n', start=cursor, timeout=90)
        report['checks'].append({'name': 'partial_launch_pair_failure_atomic_cleanup', 'status': 'passed'})
        guest.expect(b'DYNAMIC_TERMINAL_BUDGET_PASS\n', start=cursor, timeout=30)
        guest.expect(b'DYNAMIC_TERMINAL_ALL_PASS cases=13 native_groups=2\n', start=cursor, timeout=30)
        report['checks'].append({'name': 'native_cumulative_budget_no_extension_bypass', 'status': 'passed'})
        guest.close(); guest = None
        report['owner_death_phases'] = {}
        for name, trigger, control in (('owner_exit_calibration', b'C', True), ('terminal_owner_exit', b'D', False)):
            phase = out / name; phase.mkdir()
            nonce = secrets.token_bytes(32)
            nonce_file = phase / 'nonce.bin'; nonce_file.write_bytes(nonce); bind(nonce_file)
            # QEMU is stopped during every import/export. A fresh nonce prevents
            # accepting the preceding cold disk's otherwise valid receipt.
            transfer(disk, 'import', '/tests/terminal_nonce', nonce_file)
            item = {'status': 'failed', 'nonce_sha256': sha(nonce_file), 'disk_before_sha256': sha(disk),
                    'global_resource_samples': []}
            report['owner_death_phases'][name] = item
            guest = Guest(args.system / 'xos-install.iso', name, work_disk=disk,
                          iso=True, qmp_enabled=True, log_dir=phase)
            item['qemu_command'] = guest.command
            guest.expect(b'xos64> ', timeout=40); send_bytes(guest, b'run\r')
            guest.expect(b'DYNAMIC_TERMINAL_BOOT_READY', timeout=40); send_bytes(guest, trigger)
            # COM1 stays detached after the real bootstrap owner exits. The
            # observer has a 30-second native deadline and a 5-second sync
            # deadline; bounded host time also covers slow TCG scheduling.
            for interval in range(6):
                pump(guest, 15)
                print('owner observer', name, 'host seconds', (interval + 1) * 15, flush=True)
                if interval in (4, 5):
                    sample = sample_kernel_resources(guest, kernel_resources, phase / 'kernel_resources',
                                                     'after_' + str((interval + 1) * 15) + 's_pump')
                    item['global_resource_samples'].append(sample)
                    for path, expected in sample['raw_files'].items(): bind(path, expected)
            guest.close(); guest = None
            item['disk_after_sha256'] = sha(disk)
            receipt = phase / 'owner_report.bin'
            transfer(disk, 'export', '/tests/terminal_owner_report', receipt)
            synced = phase / 'owner_synced.bin'
            transfer(disk, 'export', '/tests/terminal_owner_synced', synced)
            if synced.read_bytes() != nonce:
                raise AssertionError('the report has no matching witness after a successful native sync')
            item['receipt_sha256'] = sha(receipt)
            item['synced_nonce_sha256'] = sha(synced)
            item['receipt'] = owner_receipt(receipt.read_bytes(), nonce, control)
            item['global_resources'] = verify_kernel_resource_pair(item['global_resource_samples'],
                native={key: item['receipt']['final'][key] for key in ('free_pages', 'tasks')})
            item['status'] = 'passed'
            report['checks'].append({'name': name, 'status': 'passed', 'receipt_sha256': item['receipt_sha256']})
            (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            print('PASS', name, flush=True)
        calibration = report['owner_death_phases']['owner_exit_calibration']['receipt']
        observed = report['owner_death_phases']['terminal_owner_exit']['receipt']
        comparison = ('free_pages', 'tasks', 'observer_thread_results', 'observer_user_pages',
                      'observer_kernel_stack_pages', 'observer_channels', 'observer_pipe_references',
                      'observer_threads', 'observer_reserved_threads', 'observer_waiting_threads')
        if any(calibration['final'][key] != observed['final'][key] for key in comparison):
            raise AssertionError('owner-death final observer+Files state differs from independently measured calibration')
        global_calibration = report['owner_death_phases']['owner_exit_calibration']['global_resources']
        global_observed = report['owner_death_phases']['terminal_owner_exit']['global_resources']
        if global_calibration != global_observed:
            raise AssertionError('owner-death global pages/tasks/completions differ from the cold-boot calibration')
        report['owner_death_resource_scope'] = {
            'comparison': list(comparison), 'exact_cold_boot_calibration_match': True,
            'native_statistics': 'checked existing thread statistics and self resource observation',
            'global_statistics': 'two stable read-only QMP snapshots bound to the exact kernel ELF and sources',
            'global_comparison': ['free_pages', 'tasks', 'completions'],
            'global_final': global_observed,
            'owner_exit_only': True, 'owner_kill_or_com1_recovery_claimed': False,
            'net_pages_returned_calibration': calibration['net_pages_returned_from_pre_actor_owner_observer_state'],
            'net_pages_returned_target': observed['net_pages_returned_from_pre_actor_owner_observer_state']}
        verify_all()
        report['status'] = 'passed'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        if guest: guest.close()
        if disk.exists():
            report['work_disk_after_sha256'] = sha(disk)
            disk.unlink()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        evidence = {p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob('*'))
                    if p.is_file() and p.name != 'evidence_manifest.json'}
        (out / 'evidence_manifest.json').write_text(json.dumps({'status': report['status'], 'files': evidence}, indent=2) + '\n')


if __name__ == '__main__':
    main()
