#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the bounded W1 wait probe against a committed system and private disk."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command
from sdk_receipt import verify_sdk
from task_smoke import send_bytes
from toolchain import COMMON_FLAGS, X86_FLAGS, tool
from work_disk import transfer


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', choices=('wait', 'channel', 'pio', 'irq', 'tty_exec', 'device'), default='wait')
    parser.add_argument('--system', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'],
                               cwd=ROOT, text=True).strip():
        raise SystemExit('Commit all work before guest acceptance')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    system = args.system.resolve(strict=True)
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(ROOT / 'src') or output.is_relative_to(ROOT / 'localpilot') or output.is_relative_to(system):
        raise SystemExit('output must be a new private directory')
    manifest = json.loads((system / 'manifest.json').read_text())
    for name, expected in manifest['sources'].items():
        if sha(ROOT / name) != expected:
            raise SystemExit('system source differs from checkout: ' + name)
    image = system / 'xos-install.iso'
    if sha(image) != manifest['artifacts']['xos-install.iso']['sha256']:
        raise SystemExit('system image differs from manifest')
    sdk = system / 'sdk'
    sdk_receipt = verify_sdk(sdk, manifest)
    output.mkdir(parents=True)
    fixture_name = {'pio': 'pio_negative', 'irq': 'irq_negative', 'tty_exec': 'terminal_exec'}.get(args.probe, args.probe)
    fixture = ROOT / ('tests/fixtures/ncursesw/' + fixture_name + '_probe.cpp')
    if args.probe == 'device':
        fixture = ROOT / 'tests/fixtures/device_abi_probe.cpp'
    obj, elf = output / 'wait_probe.o', output / 'wait_probe.elf'
    commands = [[tool('g++'), *COMMON_FLAGS, *X86_FLAGS, *(['-w'] if args.probe == 'tty_exec' else []), '-I', str(sdk / 'include'),
                 '-c', str(fixture), '-o', str(obj)],
                [tool('g++'), *X86_FLAGS, '-nostdlib', '-static', '-no-pie',
                 '-Wl,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096',
                 '-T', str(sdk / 'user.ld'), str(sdk / ('crt0_libc.o' if args.probe == 'tty_exec' else
                                                        'crt0_posix.o' if args.probe == 'device' else 'crt0.o')), str(obj),
                 '-Wl,--start-group', str(sdk / 'lib/libxos_loader.a'),
                 str(sdk / 'lib/libxos.a'),
                 *([str(sdk / 'lib/libc.a'), str(sdk / 'lib/libm.a'), '-lgcc'] if args.probe in ('tty_exec', 'device') else []),
                 '-Wl,--end-group', '-o', str(elf)]]
    report = {'status': 'failed', 'probe': args.probe, 'revision': revision, 'build_id': manifest['build_id'],
              'system_manifest_sha256': sha(system / 'manifest.json'), 'image_sha256': sha(image),
              'sdk_tree_sha256': sdk_receipt['tree_sha256'], 'fixture_sha256': sha(fixture),
              'probe_script_sha256': sha(Path(__file__)),
              'commands': commands, 'checks': [],
              'not_run': ['foreground_ownership', 'console_concurrent_close', 'failure_recovery',
                          'legacy_console_deadline_wait', 'overflow', 'unicode', 'terminfo',
                          'ncurses', 'resource_stress']}
    if args.probe == 'channel':
        report['not_run'] = ['fork_pair_security_matrix', 'fault_cleanup',
                             'concurrent_senders', 'resource_stress', 'full_w1_terminal']
    elif args.probe in ('pio', 'irq'):
        report['not_run'] = ['authorized_boundaries', 'fork_exec', 'revocation_races',
                             'cross_process_isolation', 'resource_stress', 'full_w1_terminal']
    elif args.probe == 'tty_exec':
        report['not_run'] = ['fork_inheritance_stress_and_failure', 'threaded_profile',
                             'exec_inflight_races', 'full_w1_terminal']
    elif args.probe == 'device':
        report['not_run'] = ['device_grant', 'device_map', 'device_irq', 'device_dma', 'full_w1_terminal']
    guest = None
    try:
        for cmd in commands:
            subprocess.run(cmd, check=True)
        report['elf_sha256'] = sha(elf)
        with tempfile.TemporaryDirectory(prefix='xos_w1_wait_') as temporary:
            disk = Path(temporary) / 'disk.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/' + ('ttyexec' if args.probe == 'tty_exec' else args.probe) + '.elf', elf)
            if args.probe == 'tty_exec':
                terminal = system / 'user_terminal.image.elf'
                if sha(terminal) != manifest['artifacts'][terminal.name]['sha256']:
                    raise SystemExit('terminal artifact differs from manifest')
                transfer(disk, 'import', '/bin/terminal.elf', terminal)
                legacy = system / 'user_libc_hello.image.elf'
                if sha(legacy) != manifest['artifacts'][legacy.name]['sha256']:
                    raise SystemExit('legacy artifact differs from manifest')
                transfer(disk, 'import', '/bin/legacy.elf', legacy)
            guest = Guest(image, 'w1_wait', work_disk=disk, iso=True)
            report['qemu_command'] = guest.command
            guest.expect(b'xos64> ', timeout=40)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=40)
            if args.probe == 'tty_exec':
                command(guest, 'demo quiet', b'demo tasks')
            else:
                command(guest, 'demo keep', b'demo: keep')
                for pid in (1, 3, 4):
                    command(guest, f'kill {pid}', b'kill: accepted')
            if args.probe == 'channel':
                reply = command(guest, 'exec-driver /bin/channel.elf', b'W1_CHANNEL_OK', timeout=40)
                if b'kind=exited code=0' not in reply:
                    raise AssertionError('channel probe did not exit successfully')
                report['checks'].append('channel_bounded_lifecycle_subset')
                report['checks'].append('explicit_exec_preserve_and_failed_duplicate_unchanged')
                report['checks'].append('channel_wait_many_validation_timeout_and_wakeup')
                report['checks'].append('channel_wait_many_blocked_peer_close_and_revalidation')
                report['checks'].append('channel_single_receiver_blocked_peer_close_and_revalidation')
                report['checks'].append('channel_single_sender_blocked_peer_close_and_revalidation')
                report['checks'].append('channel_fork_pair_identity_duplicate_and_abort')
                report['checks'].append('channel_fork_pair_invalid_direction_child_and_request')
                report['checks'].append('channel_fork_pair_peer_provenance_validation')
                report['checks'].append('channel_fork_pair_commit_child_io_and_exit_cleanup')
            elif args.probe == 'tty_exec':
                start = len(guest.output)
                send_bytes(guest, b'tty-run /bin/ttyexec.elf\r')
                guest.expect(b'TTY_EXEC_BEFORE pid=', start=start, timeout=60)
                guest.expect(b'TTY_EXEC_AFTER pid=', start=start, timeout=60)
                guest.expect(b'kind=exited code=0', start=start, timeout=60)
                guest.expect(b'xsh> ', start=start, timeout=60)
                data = bytes(guest.output[start:])
                before = re.search(rb'TTY_EXEC_BEFORE pid=(\d+)', data)
                after = re.search(rb'TTY_EXEC_AFTER pid=(\d+)', data)
                if not before or not after or before.group(1) != after.group(1):
                    raise AssertionError('terminal exec did not preserve process identity')
                report['checks'].append('terminal_exec_identity_mode_alias_cloexec_and_failed_exec')
                start = len(guest.output)
                send_bytes(guest, b'tty-run /bin/ttyexec.elf drop\r')
                guest.expect(b'TTY_EXEC_DROP_READY', start=start, timeout=60)
                guest.expect(b'kind=exited code=0', start=start, timeout=60)
                guest.expect(b'xsh> ', start=start, timeout=60)
                report['checks'].append('terminal_exec_all_cloexec_closed')
                start = len(guest.output)
                send_bytes(guest, b'tty-run /bin/ttyexec.elf fork\r')
                guest.expect(b'TTY_FORK_CHILD', start=start, timeout=60)
                guest.expect(b'TTY_FORK_PARENT', start=start, timeout=60)
                guest.expect(b'kind=exited code=0', start=start, timeout=60)
                guest.expect(b'xsh> ', start=start, timeout=60)
                report['checks'].append('terminal_fork_alias_shared_mode_and_child_exit')
                start = len(guest.output)
                send_bytes(guest, b'tty-run /bin/ttyexec.elf fork-exec\r')
                guest.expect(b'TTY_FORK_EXEC_BEFORE pid=', start=start, timeout=60)
                guest.expect(b'TTY_EXEC_AFTER pid=', start=start, timeout=60)
                guest.expect(b'TTY_FORK_EXEC_PARENT pid=', start=start, timeout=60)
                guest.expect(b'kind=exited code=0', start=start, timeout=60)
                guest.expect(b'xsh> ', start=start, timeout=60)
                data = bytes(guest.output[start:])
                before = re.search(rb'TTY_FORK_EXEC_BEFORE pid=(\d+)', data)
                after = re.search(rb'TTY_EXEC_AFTER pid=(\d+)', data)
                if not before or not after or before.group(1) != after.group(1):
                    raise AssertionError('forked terminal exec did not preserve child identity')
                report['checks'].append('terminal_fork_exec_child_identity_alias_mode_and_failure')
                start = len(guest.output)
                send_bytes(guest, b'tty-run /bin/ttyexec.elf capacity\r')
                guest.expect(b'TTY_FORK_CAP_OK', start=start, timeout=90)
                guest.expect(b'kind=exited code=0', start=start, timeout=60)
                guest.expect(b'xsh> ', start=start, timeout=60)
                report['checks'].append('terminal_fork_capacity_failure_and_recovery')
                start = len(guest.output)
                send_bytes(guest, b'tty-run /bin/ttyexec.elf interrupt\r')
                guest.expect(b'TTY_CHILD_INTERRUPT', start=start, timeout=60)
                guest.expect(b'TTY_PARENT_INTERRUPTED', start=start, timeout=60)
                guest.expect(b'kind=exited code=0', start=start, timeout=60)
                guest.expect(b'xsh> ', start=start, timeout=60)
                report['checks'].append('terminal_fork_child_write_interrupts_parent_read')
                start = len(guest.output)
                send_bytes(guest, b'tty-run /bin/ttyexec.elf interrupt-close\r')
                guest.expect(b'TTY_PARENT_CLOSE_INTERRUPTED', start=start, timeout=60)
                guest.expect(b'kind=exited code=0', start=start, timeout=60)
                guest.expect(b'xsh> ', start=start, timeout=60)
                report['checks'].append('terminal_fork_child_exit_interrupts_parent_read')
                start = len(guest.output)
                send_bytes(guest, b'tty-run /bin/ttyexec.elf malformed-child\r')
                guest.expect(b'TTY_HEALTHY_SIBLING', start=start, timeout=60)
                guest.expect(b'TTY_BAD_CHILD_ISOLATED', start=start, timeout=60)
                guest.expect(b'kind=exited code=0', start=start, timeout=60)
                guest.expect(b'xsh> ', start=start, timeout=60)
                report['checks'].append('terminal_malformed_child_parent_and_sibling_isolation')
                # Repeat actual quota exhaustion and recovery in the same guest,
                # checking the system baseline after each completed session.
                def tty_resources():
                    mark = len(guest.output)
                    send_bytes(guest, b'stats\r')
                    guest.expect(b'[resources] free=', start=mark, timeout=30)
                    guest.expect(b'xsh> ', start=mark, timeout=30)
                    match = re.search(rb'\[resources\] free=(\d+) tasks=(\d+) completions=(\d+)',
                                      bytes(guest.output[mark:]))
                    if not match:
                        raise AssertionError('missing terminal resource counters')
                    return tuple(map(int, match.groups()))

                baseline = tty_resources()
                observed = []
                for _ in range(8):
                    mark = len(guest.output)
                    send_bytes(guest, b'tty-run /bin/ttyexec.elf capacity\r')
                    guest.expect(b'TTY_FORK_CAP_OK', start=mark, timeout=90)
                    guest.expect(b'kind=exited code=0', start=mark, timeout=60)
                    guest.expect(b'xsh> ', start=mark, timeout=60)
                    observed.append(tty_resources())
                    if observed[-1] != baseline:
                        raise AssertionError(f'terminal resource baseline changed: {baseline} -> {observed[-1]}')
                report['capacity_baseline'] = baseline
                report['capacity_after_iterations'] = observed
                report['checks'].append('terminal_fork_capacity_eight_recoveries_resource_baseline')
            elif args.probe == 'device':
                reply = command(guest, 'exec-file /bin/device.elf', b'DEVICE_ABI_PROBE ok', timeout=40)
                if b'kind=exited code=0' not in reply or b'DEVICE_ABI_PROBE_FAIL' in reply:
                    raise AssertionError('device ABI probe did not pass')
                report['checks'].append('device_abi_header_validation_and_unimplemented_grant')
            elif args.probe in ('pio', 'irq'):
                expected = b'W1_PIO_DENIED_OK' if args.probe == 'pio' else b'W1_IRQ_DENIED_OK'
                reply = command(guest, f'exec-file /bin/{args.probe}.elf', expected, timeout=40)
                if b'kind=exited code=0' not in reply:
                    raise AssertionError(args.probe + ' denial probe did not exit successfully')
                report['checks'].append(args.probe + '_unprivileged_operations_denied')
                if args.probe == 'pio':
                    reply = command(guest, 'exec-file /bin/pio.elf port', b'W1_PIO_FAULT_READY', timeout=40)
                    if b'kind=faulted' not in reply or b'vector=13' not in reply or b'W1_PIO_UNEXPECTED_ACCESS' in reply:
                        raise AssertionError('unprivileged COM1 port access did not fault with #GP')
                    report['checks'].append('unprivileged_com1_access_faults')
            else:
                pipe_output = command(guest, 'exec-file /bin/wait.elf', b'W1_PIPE_WAIT_OK', timeout=40)
                if b'kind=exited code=0' not in pipe_output:
                    raise AssertionError('pipe probe did not exit successfully')
                report['checks'].append('pipe_timeout_ready_and_close')
            if sha(image) != report['image_sha256'] or verify_sdk(sdk, manifest)['tree_sha256'] != report['sdk_tree_sha256']:
                raise RuntimeError('system or SDK changed during test')
            if sha(fixture) != report['fixture_sha256'] or sha(Path(__file__)) != report['probe_script_sha256']:
                raise RuntimeError('probe inputs changed during test')
            if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'],
                                       cwd=ROOT, text=True).strip():
                raise RuntimeError('checkout changed during test')
            if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != revision:
                raise RuntimeError('revision changed during test')
            report['status'] = 'passed_subset'
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        if guest is not None:
            (output / 'serial.log').write_bytes(guest.output)
            report['serial_sha256'] = sha(output / 'serial.log')
            guest.close()
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
