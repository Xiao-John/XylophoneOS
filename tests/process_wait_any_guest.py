#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify native wait-any against a source-bound system and actual child processes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from dash_c3_exec_smoke import exec_opt_in
from glibc_g1_probe import clean_build_environment, tool_identity
from make_work_disk import create_fat32
from process_smoke import command, resources
from shell_launch_support import bind_system
from task_smoke import send_bytes, pump
from toolchain import COMMON_FLAGS, X86_FLAGS
from work_disk import transfer


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def system_identity(system):
    """Freeze one validated system identity, including its manifest bytes."""
    manifest_path = system / 'manifest.json'
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if bind_system(system) != manifest or manifest_path.read_bytes() != manifest_bytes:
        raise RuntimeError('system manifest changed while binding acceptance inputs')
    identity = {'build_id': manifest['build_id'],
                'source_sha256': manifest['source_sha256'],
                'system_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest()}
    for name, key in [('xos-install.iso', 'iso_sha256'), ('sdk/manifest.json', 'sdk_manifest_sha256')]:
        actual = sha(system / name)
        if actual != manifest['artifacts'][name]['sha256']:
            raise RuntimeError('system artifact changed while binding acceptance inputs: ' + name)
        identity[key] = actual
    return identity


def verify_system_identity(system, expected):
    current = system_identity(system)
    for name, value in current.items():
        if value != expected[name]:
            raise RuntimeError('system identity changed during acceptance: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeat', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeat <= 5:
        parser.error('repeat must be in 1..5')
    system = args.system.resolve(strict=True)
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'runs': [], 'checks': [], 'commands': [],
              'scope': 'native sys20 + native worker core; existing newlib exec receiver'}
    guest = None

    def save():
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    try:
        initial_system = system_identity(system)
        report.update(initial_system)
        report['tools'] = {name: tool_identity(name) for name in ('x86_64-elf-g++', 'qemu-system-x86_64')}
        environment, removed = clean_build_environment(os.environ)
        environment['LC_ALL'] = 'C'
        report['sanitized_environment'] = removed
        compiler = report['tools']['x86_64-elf-g++']['path']
        compiler_headers = subprocess.check_output([compiler, '-print-file-name=include'], text=True,
                                                    env=environment).strip()
        libgcc = Path(subprocess.check_output([compiler, '-print-libgcc-file-name'], text=True,
                                              env=environment).strip())
        sdk = system / 'sdk'
        archives = [sdk / 'lib/libxos.a', sdk / 'lib/libxos_loader.a',
                    sdk / 'lib/libc.a', sdk / 'lib/libm.a', libgcc,
                    system / 'threading_core/libxos_thread_core.a']
        report['link_inputs'] = {str(path): sha(path) for path in archives}
        report['sources'] = {str(Path(__file__).resolve().relative_to(ROOT)): sha(Path(__file__).resolve())}
        # The mechanism-only worker header is intentionally excluded from the
        # single-thread application SDK. Keep this test's explicit profile local.
        core_header = ROOT / 'src/user/include/xos/thread_core.hpp'
        private_include = output / 'include'
        (private_include / 'xos').mkdir(parents=True)
        shutil.copyfile(core_header, private_include / 'xos/thread_core.hpp')
        report['sources'][str(core_header.relative_to(ROOT))] = sha(core_header)
        report['elfs'] = {}
        for name, source_name, crt in [('wait_any', 'probe.cpp', 'crt0.o'),
                                        ('wait_exec', 'exec_receiver.cpp', 'crt0_posix.o')]:
            source = ROOT / 'tests/fixtures/process_wait' / source_name
            report['sources'][str(source.relative_to(ROOT))] = sha(source)
            obj, binary = output / (name + '.o'), output / (name + '.elf')
            commands = [[compiler, *COMMON_FLAGS, *X86_FLAGS, '-fno-builtin', '-nostdinc',
                         '-I', str(private_include),
                         '-isystem', str(sdk / 'include'), '-isystem', compiler_headers,
                         '-c', str(source), '-o', str(obj)],
                        [compiler, *X86_FLAGS, '-nostdlib', '-static', '-no-pie',
                         '-Wl,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096',
                         '-T', str(sdk / 'user.ld'), str(sdk / crt), str(obj),
                         '-Wl,--start-group', *map(str, archives), '-Wl,--end-group', '-o', str(binary)]]
            with (output / (name + '.build.log')).open('w') as log:
                for invocation in commands:
                    subprocess.run(invocation, cwd=ROOT, env=environment, stdout=log,
                                   stderr=subprocess.STDOUT, check=True)
            report['elfs'][name] = {'sha256': sha(binary), 'commands': commands,
                                    'crt_sha256': sha(sdk / crt), 'source_sha256': sha(source)}
        if not exec_opt_in(output / 'wait_exec.elf'):
            raise RuntimeError('existing newlib receiver must advertise actual startup-v3 support')
        with tempfile.TemporaryDirectory(prefix='xos_wait_any_') as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            for name in report['elfs']:
                transfer(disk, 'import', '/bin/' + name, output / (name + '.elf'))
            report['work_disk_initial_sha256'] = sha(disk)
            verify_system_identity(system, initial_system)
            guest = Guest(system / 'xos-install.iso', 'process_wait_any',
                          work_disk=disk, iso=True, qmp_enabled=False)
            report['qemu_command'] = guest.command
            guest.expect(b'xos64> ', timeout=40)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=40)
            command(guest, 'demo quiet', b'demo tasks')
            command(guest, 'audio stop', b'xsh> ')
            pump(guest, 0.2)
            baseline = resources(guest)
            report['resource_baseline'] = baseline

            def recovered():
                for _ in range(30):
                    state = resources(guest)
                    if state == baseline:
                        return state
                    pump(guest, 0.1)
                raise AssertionError(('resource recovery', baseline, state))

            cases = [('sequential', 'sequential'), ('fork', 'fork-publication'),
                     ('exact-any', 'exact-any'), ('two-any', 'two-any'),
                     ('last-child', 'last-child'), ('fault-kill', 'fault-kill'),
                     ('exec', 'exec-existing'), ('orphan', 'orphan-parent')]
            for repeat in range(args.repeat):
                for mode, marker in cases:
                    line = 'exec-driver /bin/wait_any ' + mode
                    captured = command(guest, line, b'kind=exited code=', timeout=75)
                    if b'WAIT_ANY_PASS ' + marker.encode() not in captured:
                        raise AssertionError(captured[-5000:])
                    outcomes = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', captured)
                    if outcomes != [b'0'] or b'WAIT_ANY_FAIL' in captured:
                        raise AssertionError(captured[-5000:])
                    report['commands'].append(line)
                    report['runs'].append({'mode': mode, 'repeat': repeat,
                                           'resources_after': recovered(), 'exit_code': 0})
                    save()
                start = len(guest.output)
                send_bytes(guest, b'exec-driver /bin/wait_any cancel\r')
                guest.expect(b'WAIT_ANY_BLOCKED', start=start, timeout=60)
                pump(guest, 0.1)
                send_bytes(guest, b'\x1b')
                guest.expect(b'kind=killed', start=start, timeout=30)
                guest.expect(b'xsh> ', start=start, timeout=30)
                report['runs'].append({'mode': 'cancel', 'repeat': repeat,
                                       'resources_after': recovered(), 'outcome': 'killed'})
                save()
            report['checks'] = ['explicit flags and unchanged failure output', 'blocking/nohang/empty',
                                'building and fork publication', 'authenticated parent ownership',
                                'exact/any and two-any unique consumption', 'last-child competitor wake',
                                'fault/kill status identity', 'exec preserves existing children without PID cache',
                                'orphan and foreground cancellation lifecycle', 'exact resource recovery each run']
            report['work_disk_final_sha256'] = sha(disk)
        verify_system_identity(system, initial_system)
        for relative, expected in report['sources'].items():
            if sha(ROOT / relative) != expected:
                raise RuntimeError('guest source changed during acceptance')
        for path, expected in report['link_inputs'].items():
            if sha(Path(path)) != expected:
                raise RuntimeError('native link input changed during acceptance')
        report['status'] = 'passed'
        print('PASS native wait-any', len(report['runs']), 'guest runs;', len(report['checks']), 'groups')
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        if guest is not None:
            guest.close()
            (output / 'serial.log').write_bytes(guest.output)
            report['serial_sha256'] = sha(output / 'serial.log')
        save()


if __name__ == '__main__':
    main()
