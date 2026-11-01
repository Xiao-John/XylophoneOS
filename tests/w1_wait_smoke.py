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
    parser.add_argument('--probe', choices=('wait', 'channel', 'pio', 'irq', 'tty_exec'), default='wait')
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
    obj, elf = output / 'wait_probe.o', output / 'wait_probe.elf'
    commands = [[tool('g++'), *COMMON_FLAGS, *X86_FLAGS, *(['-w'] if args.probe == 'tty_exec' else []), '-I', str(sdk / 'include'),
                 '-c', str(fixture), '-o', str(obj)],
                [tool('g++'), *X86_FLAGS, '-nostdlib', '-static', '-no-pie',
                 '-Wl,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096',
                 '-T', str(sdk / 'user.ld'), str(sdk / ('crt0_libc.o' if args.probe == 'tty_exec' else 'crt0.o')), str(obj),
                 '-Wl,--start-group', str(sdk / 'lib/libxos_loader.a'),
                 str(sdk / 'lib/libxos.a'),
                 *([str(sdk / 'lib/libc.a'), str(sdk / 'lib/libm.a'), '-lgcc'] if args.probe == 'tty_exec' else []),
                 '-Wl,--end-group', '-o', str(elf)]]
    report = {'status': 'failed', 'probe': args.probe, 'revision': revision, 'build_id': manifest['build_id'],
              'system_manifest_sha256': sha(system / 'manifest.json'), 'image_sha256': sha(image),
              'sdk_tree_sha256': sdk_receipt['tree_sha256'], 'fixture_sha256': sha(fixture),
              'commands': commands, 'checks': [],
              'not_run': ['foreground_ownership', 'console_concurrent_close', 'failure_recovery',
                          'legacy_console_deadline_wait', 'overflow', 'unicode', 'terminfo',
                          'ncurses', 'resource_stress']}
    if args.probe == 'channel':
        report['not_run'] = ['fork', 'fault_cleanup', 'blocked_waiter_close',
                             'concurrent_senders', 'resource_stress', 'full_w1_terminal']
    elif args.probe in ('pio', 'irq'):
        report['not_run'] = ['authorized_boundaries', 'fork_exec', 'revocation_races',
                             'cross_process_isolation', 'resource_stress', 'full_w1_terminal']
    elif args.probe == 'tty_exec':
        report['not_run'] = ['fork_inheritance', 'threaded_profile', 'all_cloexec',
                             'exec_inflight_races', 'full_w1_terminal']
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
            guest.close()
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
