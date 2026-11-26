#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify the complete static XOS glibc SDK through public APIs in QEMU."""
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
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_glibc_sdk import inputs as glibc_inputs
from dash_c3_exec_smoke import exec_opt_in
from glibc_g1_probe import clean_build_environment
from make_work_disk import create_fat32
from process_smoke import command, resources
from shell_launch_support import bind_tool
from task_smoke import send_bytes, pump
from work_disk import transfer


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def system_sources():
    paths = [ROOT / name for name in ('Makefile', 'VERSION', 'LICENSE', 'NOTICE')]
    paths.extend(path for path in sorted((ROOT / 'licenses').glob('*')) if path.is_file())
    suffixes = ('.asm', '.s', '.sh', '.inc', '.py', '.cpp', '.hpp', '.c', '.h',
                '.ld', '.json', '.lldb', '.patch')
    for folder in ('src', 'scripts', 'tests', 'config'):
        paths.extend(path for path in sorted((ROOT / folder).rglob('*')) if path.suffix in suffixes)
    return {str(path.relative_to(ROOT)): sha(path) for path in paths}


def suite_cases(suite):
    cases = []
    if suite in ('g2', 'all'):
        markers = ['G2 main ok:', 'G2 buffered exit', 'G2 atexit second',
                   'G2 atexit first', 'G2 destructor ok']
        cases.extend([
            ('g2_return', 'glibc_g2/static_main.c', ['alpha'], 37, markers),
            ('g2_exit', 'glibc_g2/static_main.c', ['alpha', 'exit'], 39, markers),
            ('g2_fatal_stderr', 'glibc_g2/fatal_stderr.c', [], 127,
             ['G2 fatal stderr begin:' + '.' * 300 + ':G2 fatal stderr end']),
            ('g2_ctor_order', 'glibc_g2/ctor_order.c', [], 0, ['GLIBC_CTOR_ORDER_PASS']),
        ])
    if suite in ('threads', 'all'):
        cases.extend([
            ('g3_threads', 'glibc_g3/threads.c', [], 0,
             ['G3-T PASS unsupported attributes', 'G3-T PASS TLS errno',
              'G3-T PASS monotonic and realtime bounded waits', 'G3-T PASS complete']),
            ('g3_last_thread', 'glibc_g3/last_thread_exit.c', [], 0,
             ['G3-T PASS initial pthread_exit join TSD and final-worker atexit']),
            ('g3_detached', 'glibc_g3/detached_threads.c', [], 0,
             ['G3-T PASS detached creation detach TSD slots kernel-stack recovery rounds=16']),
            ('g3_active_exit', 'glibc_g3/blocked_stdio_exit.c', [], 127,
             ['G3-T BEGIN active worker owns stdout', 'G3-X callback before blocked flush',
              'event=exit_cleanup_timeout']),
        ])
    if suite in ('exit', 'all'):
        normal_markers = ['G3-X BEGIN active peers and buffered files',
                          'G3-X worker buffered', 'G3-X callback second',
                          'G3-X callback first', 'G3-X fini and complete stdout flush']
        cases.extend([
            ('g3_exit_return', 'glibc_g3/active_exit.c', [], 37, normal_markers),
            ('g3_exit_return_verify', 'glibc_g3/active_exit.c', ['verify'], 0,
             ['G3-X PASS process-exit file flush bytes and resource release']),
            ('g3_exit_explicit', 'glibc_g3/active_exit.c', ['exit'], 39, normal_markers),
            ('g3_exit_explicit_verify', 'glibc_g3/active_exit.c', ['verify'], 0,
             ['G3-X PASS process-exit file flush bytes and resource release']),
            ('g3_exit_concurrent', 'glibc_g3/exit_protocol.c', ['concurrent'], 37,
             ['G3-X callback first once', 'G3-X concurrent caller preserved owner status',
              'G3-X callback last once']),
            ('g3_exit_recursive', 'glibc_g3/exit_protocol.c', ['recursive'], 43,
             ['G3-X callback first once', 'G3-X callback last once']),
            ('g3_exit_worker', 'glibc_g3/exit_protocol.c', ['worker'], 41,
             ['G3-X callback first once', 'G3-X callback last once']),
            ('g3_exit_quick', 'glibc_g3/exit_protocol.c', ['quick'], 45,
             ['G3-X quick callback first', 'G3-X quick callback last']),
            ('g3_exit_abi', 'glibc_g3/exit_protocol.c', ['abi'], 125,
             ['G3-X owner stop-peers denied and original timeout retained',
              'G3-X PASS ABI rejection ownership peer cleanup and fixed deadline',
              'event=exit_cleanup_timeout']),
            ('g3_exit_legacy', 'glibc_g3/exit_protocol.c', ['legacy'], 46,
             ['G3-X legacy stop-peers first call and reentry preserved']),
            ('g3_exit_fault', 'glibc_g3/exit_protocol.c', ['fault'], ('faulted', 0),
             ['G3-X owner fault ready', 'event=fault', 'vector=6']),
            ('g3_exit_abandon', 'glibc_g3/exit_protocol.c', ['abandon'], 127,
             ['G3-X owner abandon ready']),
        ])
        if suite == 'exit':
            cases.append(('g3_active_exit', 'glibc_g3/blocked_stdio_exit.c', [], 127,
                          ['G3-T BEGIN active worker owns stdout',
                           'G3-X callback before blocked flush', 'event=exit_cleanup_timeout']))
    if suite in ('files', 'all'):
        cases.extend([
            ('g3_files_single', 'glibc_g3/files_public_probe.c', ['single'], 0,
             ['GLIBC_G3_FILES_PASS', 'threaded=0']),
            ('g3_files_threads', 'glibc_g3/files_public_probe.c', [], 0,
             ['GLIBC_G3_FILES_PASS', 'threaded=1']),
        ])
    if suite in ('files-extra', 'all'):
        cases.append(('g3_files_extra', 'glibc_g3/files_extra_public_probe.c', [], 0,
                      ['GLIBC_FILES_EXTRA_POSITIONED_PASS', 'GLIBC_FILES_EXTRA_DIRECTORY_PASS',
                       'GLIBC_FILES_EXTRA_PASS']))
    if suite in ('path-mutations', 'all'):
        cases.append(('g3_path_mutations', 'glibc_g3/path_mutations.c', [], 0,
                      ['GLIBC_PATH_MUTATION_PASS']))
    if suite in ('cwd', 'all'):
        cases.append(('g3_cwd', 'glibc_g3/cwd_probe.c', ['/'], 0, ['GLIBC_CWD_ACCESS_PASS']))
    if suite in ('process', 'all'):
        cases.append(('g3_spawn', 'glibc_g3/process_spawn.c', ['parent'], 0,
                      ['GLIBC_SPAWN_CHILD_0', 'GLIBC_SPAWN_CHILD_23', 'GLIBC_SPAWN_WAIT_PASS']))
    if suite in ('pipe', 'all'):
        cases.append(('g3_pipe', 'glibc_g3/pipe_probe.c', [], 0,
                      ['GLIBC_PIPE_NONBLOCK_PASS', 'GLIBC_PIPE_CAPACITY_PASS',
                       'GLIBC_PIPE_THREAD_STDIO_PASS', 'GLIBC_PIPE_CLOEXEC_PASS']))
    return cases


def build_newlib_parent(system_build, output, report,
                       fixture='glibc_g3/files_exec_parent.c', name='g3_files_parent'):
    """Use the same system's existing SDK for an actual cross-libc exec."""
    sdk = system_build / 'sdk'
    receipt = json.loads((sdk / 'manifest.json').read_text())
    if receipt['build_id'] != report['system_build_id']:
        raise RuntimeError('newlib parent SDK and system build IDs differ')
    compiler = Path(shutil.which('x86_64-elf-gcc')).resolve(strict=True)
    env, removed = clean_build_environment(os.environ)
    env['LC_ALL'] = 'C'
    libgcc = Path(subprocess.check_output([compiler, '-print-libgcc-file-name'], env=env, text=True).strip())
    headers = subprocess.check_output([compiler, '-print-file-name=include'], env=env, text=True).strip()
    source = ROOT / 'tests/fixtures' / fixture
    binary = output / (name + '.elf')
    obj = output / (name + '.o')
    inputs = [sdk / name for name in ('crt0_posix.o', 'user.ld', 'lib/libxos.a',
              'lib/libxos_loader.a', 'lib/libc.a', 'lib/libm.a')]
    report['newlib_parent_inputs'] = {str(path.relative_to(sdk)): sha(path) for path in inputs}
    report['newlib_parent_libgcc_sha256'] = sha(libgcc)
    commands = [[str(compiler), '-std=gnu11', '-O2', '-g', '-mno-red-zone',
                 '-fno-pie', '-fno-pic', '-fno-stack-protector', '-fno-builtin', '-nostdinc',
                 '-isystem', str(sdk / 'include'), '-isystem', headers,
                 '-c', str(source), '-o', str(obj)],
                [str(compiler), '-nostdlib', '-static', '-no-pie',
                 '-Wl,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
                 '-T', str(sdk / 'user.ld'), str(sdk / 'crt0_posix.o'), str(obj),
                 '-Wl,--start-group', *map(str, inputs[2:]), str(libgcc),
                 '-Wl,--end-group', '-o', str(binary)]]
    with (output / (name + '_build.log')).open('w') as log:
        for invocation in commands:
            subprocess.run(invocation, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    for path in inputs:
        if sha(path) != report['newlib_parent_inputs'][str(path.relative_to(sdk))]:
            raise RuntimeError('newlib SDK changed while building exec parent')
    report['elfs'][name] = {'source': fixture,
        'source_sha256': sha(source), 'elf_sha256': sha(binary), 'build_commands': commands,
        'compiler_sha256': sha(compiler), 'exec_receiver_marker': exec_opt_in(binary),
        'sanitized_environment': removed}
    return binary


def service_death(build, program, output, report):
    """Exercise actual service exit in an explicitly instrumented private image."""
    guest = None
    result = report['service_death'] = {'status': 'failed', 'fault_injection': True}
    try:
        with tempfile.TemporaryDirectory(prefix='xos_glibc_files_death_') as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/g3_files', program)
            guest = Guest(build / 'xos-install.iso', 'glibc_files_death',
                          work_disk=disk, iso=True, qmp_enabled=False)
            result['qemu_command'] = guest.command
            guest.expect(b'xos64> ', timeout=30)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=30)
            command(guest, 'demo quiet', b'demo tasks')
            baseline = resources(guest)
            result['baseline'] = baseline
            listing = command(guest, 'ps', b'name=files ')
            matches = re.findall(rb'^pid=(\d+) name=files state=[^\n]+$', listing, re.MULTILINE)
            if len(matches) != 1:
                raise AssertionError('expected one live files service: ' + repr(listing))
            result['files_pid'] = int(matches[0])
            captured = command(guest, 'exec-file /bin/g3_files service-death',
                               b'kind=exited code=', timeout=60)
            if re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', captured) != [b'0']:
                raise AssertionError('service-death probe failed: ' + repr(captured))
            position = 0
            reclaimed = ('[task] event=reclaimed pid=' + str(result['files_pid']) + ' ').encode()
            for marker in (b'GLIBC_G3_FILES_DEATH_READY', reclaimed,
                           b'GLIBC_G3_FILES_DEATH_PASS'):
                found = captured.find(marker, position)
                if found < 0:
                    raise AssertionError('service-death marker missing: ' + repr(captured))
                position = found + len(marker)
            after = resources(guest)
            freed = re.findall(re.escape(reclaimed) + rb'pages=(\d+)', captured)
            if len(freed) != 1:
                raise AssertionError('missing unique service page reclamation count')
            expected = (baseline[0] + int(freed[0]), baseline[1] - 1, baseline[2])
            if after != expected:
                raise AssertionError(f'files-service death resource drift: expected {expected}, got {after}')
            remaining = command(guest, 'ps', b'name=supervisor ')
            if re.search(rb'^pid=\d+ name=files ', remaining, re.MULTILINE):
                raise AssertionError('files service is still live after fault injection')
            result.update(status='passed', resources_after_service_removed=after,
                          expected_resources_after_service_removed=expected,
                          output=captured.decode(errors='replace'))
    finally:
        if guest:
            guest.close()
            (output / 'service_death_serial.log').write_bytes(guest.output)
            result['serial_sha256'] = sha(output / 'service_death_serial.log')
    return {'case': 'g3_files_service_death', **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-build', type=Path, required=True)
    parser.add_argument('--glibc-build', type=Path, required=True)
    parser.add_argument('--death-system-build', type=Path,
                        help='private system built with --glibc-files-death-probe')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--suite', choices=('g2', 'threads', 'files', 'files-extra', 'path-mutations',
                                            'cwd', 'process', 'pipe', 'exit', 'all'),
                        default='g2')
    parser.add_argument('--dash-receipt', type=Path, help='current-system dash C3 receipt for cwd and process suites')
    parser.add_argument('--repetitions', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 10:
        parser.error('repetitions must be in 1..10')
    if args.suite in ('cwd', 'process') and args.dash_receipt is None:
        parser.error(args.suite + ' qualification requires --dash-receipt for the second launch path')
    cases = suite_cases(args.suite)
    required = {relative for _, relative, _, _, _ in cases}
    if args.suite in ('files', 'all'):
        required.add('glibc_g3/files_exec_parent.c')
    if args.suite in ('cwd', 'all'):
        required.add('glibc_g3/cwd_setup.c')
    missing = sorted(relative for relative in required
                     if not (ROOT / 'tests/fixtures' / relative).is_file())
    if missing:
        parser.error(f'guest suite {args.suite!r} unavailable: missing fixtures: '
                     + ', '.join(missing))
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        parser.error('output must be a new private directory')
    output.mkdir(parents=True)
    report = {'status': 'not_run', 'suite': args.suite, 'runs': [],
              'qmp': 'disabled; serial-only qualification',
              'active_worker_normal_exit': 'native bounded cleanup window; qualified only by exit suite',
              'dash_entry': 'not_run'}
    guest = None
    try:
        system_build = args.system_build.resolve(strict=True)
        glibc_build = args.glibc_build.resolve(strict=True)
        system_manifest = system_build / 'manifest.json'
        glibc_manifest = glibc_build / 'manifest.json'
        system = json.loads(system_manifest.read_text())
        sdk = json.loads(glibc_manifest.read_text())
        if system.get('glibc_files_death_probe', False):
            raise RuntimeError('ordinary cases require the normal system image')
        death_build = None
        if args.death_system_build:
            death_build = args.death_system_build.resolve(strict=True)
            death_manifest = death_build / 'manifest.json'
            death_system = json.loads(death_manifest.read_text())
            initial_death_manifest = sha(death_manifest)
            if death_system.get('glibc_files_death_probe') is not True:
                raise RuntimeError('service-death image lacks the explicit fault profile')
            report['service_death_inputs'] = {
                'build_id': death_system['build_id'],
                'manifest_sha256': initial_death_manifest,
                'image_sha256': sha(death_build / 'xos-install.iso')}
        if sdk.get('status') != 'static_sdk_built':
            raise RuntimeError('requires a successfully built complete static SDK')
        sysroot = glibc_build / 'sysroot'
        image = system_build / 'xos-install.iso'
        initial_system_manifest = sha(system_manifest)
        initial_sdk_manifest = sha(glibc_manifest)

        def verify_inputs():
            if sha(system_manifest) != initial_system_manifest or sha(glibc_manifest) != initial_sdk_manifest:
                raise RuntimeError('input manifest changed during qualification')
            for name, information in system['artifacts'].items():
                if sha(system_build / name) != information['sha256']:
                    raise RuntimeError('system artifact differs from its manifest: ' + name)
            if system_sources() != system['sources']:
                raise RuntimeError('system source snapshot changed')
            if glibc_inputs() != sdk['inputs']:
                raise RuntimeError('SDK input snapshot changed')
            for name, expected in sdk['artifacts'].items():
                if sha(sysroot / name) != expected:
                    raise RuntimeError('SDK artifact changed: ' + name)
            if death_build:
                if sha(death_manifest) != initial_death_manifest:
                    raise RuntimeError('service-death manifest changed')
                if death_system['sources'] != system['sources']:
                    raise RuntimeError('normal and service-death source snapshots differ')
                for name, information in death_system['artifacts'].items():
                    if sha(death_build / name) != information['sha256']:
                        raise RuntimeError('service-death artifact changed: ' + name)

        verify_inputs()
        report.update({'system_build_id': system['build_id'], 'image_sha256': sha(image),
                       'system_manifest_sha256': initial_system_manifest,
                       'glibc_manifest_sha256': initial_sdk_manifest,
                       'sdk_profile': sdk['profile'], 'elfs': {},
                       'runner_sha256': sha(Path(__file__).resolve())})
        programs = {}

        def build_glibc(name, relative, defines=()):
            source = ROOT / 'tests/fixtures' / relative
            binary = output / (name + '.elf')
            invocation = [sys.executable, str(ROOT / 'scripts/build_glibc_program.py'),
                          '--sdk', str(sysroot), '--source', str(source), '--output', str(binary)]
            for define in defines:
                invocation.extend(['--define', define])
            with (output / (name + '_build.log')).open('w') as log:
                subprocess.run(invocation, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
            programs[name] = binary
            report['elfs'][name] = {'source': relative, 'source_sha256': sha(source),
                                     'elf_sha256': sha(binary), 'build_command': invocation,
                                     'build_log_sha256': sha(output / (name + '_build.log'))}
            marker = exec_opt_in(binary)
            if bool(marker) != bool(defines):
                raise AssertionError('unexpected exec receiver opt-in: ' + name)
            report['elfs'][name]['exec_receiver_marker'] = marker

        for name, relative, _, _, _ in cases:
            build_glibc(name, relative)
        if args.suite in ('files', 'all'):
            build_glibc('g3_files_receiver', 'glibc_g3/files_public_probe.c',
                        ['XOS_GLIBC_G3_EXEC_RECEIVER'])
            programs['g3_files_parent'] = build_newlib_parent(system_build, output, report)
            cases.append(('g3_files_parent', 'glibc_g3/files_exec_parent.c',
                          ['/bin/g3_files_receiver'], 0,
                          ['GLIBC_G3_FILES_PARENT_READY', 'GLIBC_G3_FILES_INHERIT_PASS']))
        if args.suite in ('files-extra', 'all'):
            build_glibc('g3_files_extra_receiver', 'glibc_g3/files_extra_public_probe.c',
                        ['XOS_GLIBC_G3_EXEC_RECEIVER'])
            programs['g3_files_extra_parent'] = build_newlib_parent(
                system_build, output, report, 'glibc_g3/files_extra_exec_parent.c', 'g3_files_extra_parent')
            cases.append(('g3_files_extra_parent', 'glibc_g3/files_extra_exec_parent.c',
                          ['/bin/g3_files_extra_receiver'], 0,
                          ['GLIBC_FILES_EXTRA_INHERIT_DIR_PASS', 'GLIBC_FILES_EXTRA_CHILD_PASS',
                           'GLIBC_FILES_EXTRA_PARENT_PASS']))
        cwd_suite = args.suite in ('cwd', 'all')
        process_suite = args.suite in ('process', 'all')
        dash = None
        dash_scripts = {}
        if (cwd_suite or process_suite) and args.dash_receipt is not None:
            dash, report['dash_binding'] = bind_tool(args.dash_receipt, 'dash_c3', system_build / 'sdk')
        if cwd_suite:
            programs['g3_cwd_setup'] = build_newlib_parent(
                system_build, output, report, 'glibc_g3/cwd_setup.c', 'g3_cwd_setup')
            if dash is not None:
                cases.append(('g3_cwd_dash', 'glibc_g3/cwd_probe.c', [], 0,
                              ['GLIBC_CWD_ACCESS_PASS', 'GLIBC_CWD_DASH_RC=0']))
                script = output / 'cwd_via_dash.sh'
                script.write_text("cd /g3_cwd/sub || exit 2\n/bin/g3_cwd /g3_cwd/sub\n"
                                  "rc=$?\nprintf 'GLIBC_CWD_DASH_RC=%s\\n' \"$rc\"\nexit \"$rc\"\n")
                report['dash_script_sha256'] = sha(script)
                dash_scripts['/g3_cwd/cwd_via_dash.sh'] = script
        if process_suite:
            cases.append(('g3_spawn_denied', 'glibc_g3/process_spawn.c', [], 0,
                          ['GLIBC_SPAWN_DENIED_PASS']))
            if dash is not None:
                cases.append(('g3_spawn_dash', 'glibc_g3/process_spawn.c', [], 0,
                              ['GLIBC_SPAWN_CHILD_0', 'GLIBC_SPAWN_CHILD_23',
                               'GLIBC_SPAWN_WAIT_PASS', 'GLIBC_SPAWN_DASH_RC=0']))
                script = output / 'spawn_via_dash.sh'
                script.write_text("/bin/g3_spawn parent\nrc=$?\n"
                                  "printf 'GLIBC_SPAWN_DASH_RC=%s\\n' \"$rc\"\nexit \"$rc\"\n")
                report['spawn_dash_script_sha256'] = sha(script)
                dash_scripts['/g3_spawn/spawn_via_dash.sh'] = script
        verify_inputs()
        report['status'] = 'failed'
        with tempfile.TemporaryDirectory(prefix='xos_glibc_static_') as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            if args.suite in ('path-mutations', 'all'):
                # An empty FAT directory must not shadow the virtual device namespace.
                transfer(disk, 'mkdir', '/dev')
            if args.suite in ('files-extra', 'all'):
                transfer(disk, 'mkdir', '/g3_enum')
                transfer(disk, 'mkdir', '/g3_enum/sub')
            if cwd_suite:
                for directory in ('/g3_cwd', '/g3_cwd/sub', '/g3_cwd/路'):
                    transfer(disk, 'mkdir', directory)
                for name in ('plain.txt', 'read-only.txt'):
                    path = output / name
                    path.write_text('path access fixture\n')
                    transfer(disk, 'import', '/g3_cwd/' + name, path)
            if process_suite:
                transfer(disk, 'mkdir', '/g3_spawn')
                transfer(disk, 'import', '/g3_spawn/child', programs['g3_spawn'])
                plain = output / 'not_an_image.txt'
                plain.write_text('ordinary data file\n')
                transfer(disk, 'import', '/g3_spawn/plain.txt', plain)
            if dash is not None:
                transfer(disk, 'mkdir', '/usr')
                transfer(disk, 'mkdir', '/usr/bin')
                transfer(disk, 'import', '/usr/bin/dash', dash)
                for path, script in dash_scripts.items():
                    transfer(disk, 'import', path, script)
            for name, binary in programs.items():
                transfer(disk, 'import', '/bin/' + name, binary)
            guest = Guest(image, 'glibc_static_' + args.suite, work_disk=disk,
                          iso=True, qmp_enabled=False)
            report['qemu_command'] = guest.command
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=30)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=30)
            command(guest, 'demo quiet', b'demo tasks')
            baseline = resources(guest)
            report['baseline'] = baseline
            if cwd_suite:
                captured = command(guest, 'exec-file /bin/g3_cwd_setup', b'kind=exited code=')
                if b'GLIBC_CWD_READONLY_READY' not in captured or b'kind=exited code=0' not in captured:
                    raise AssertionError('FAT directory setup failed: ' + repr(captured))
                if resources(guest) != baseline:
                    raise AssertionError('FAT directory setup did not restore resources')
                report['cwd_setup'] = captured.decode(errors='replace')
            if args.suite in ('g2', 'all'):
                captured = command(guest, 'exec libc_hello', b'kind=exited code=', timeout=30)
                if b'libc says: malloc+printf 42 beef' not in captured or b'kind=exited code=7' not in captured:
                    raise AssertionError('newlib control failed: ' + repr(captured))
                if resources(guest) != baseline:
                    raise AssertionError('newlib control did not restore resources')
                report['newlib_control'] = 'passed: current-system malloc/printf/exit/resources'
            for repetition in range(args.repetitions):
                for name, _, arguments, expected_status, markers in cases:
                    launch = 'exec-driver' if name in ('g3_files_parent', 'g3_files_extra_parent') else 'exec-file'
                    line = launch + ' /bin/' + name + ''.join(' ' + arg for arg in arguments)
                    if name == 'g3_cwd_dash':
                        line = 'dash /g3_cwd/cwd_via_dash.sh'
                    elif name == 'g3_spawn':
                        line = '/bin/g3_spawn parent'
                    elif name == 'g3_spawn_denied':
                        line = 'exec-file /bin/g3_spawn denied'
                    elif name == 'g3_spawn_dash':
                        line = 'dash /g3_spawn/spawn_via_dash.sh'
                    elif name == 'g3_pipe':
                        line = '/bin/g3_pipe'
                    kind, code = ('exited', expected_status) if isinstance(expected_status, int) else expected_status
                    began = time.monotonic()
                    captured = command(guest, line, b'kind=', timeout=15 if name == 'g3_exit_abi' else 120)
                    elapsed = time.monotonic() - began
                    statuses = re.findall(rb'\[wait\] pid=\d+ kind=(\w+) code=(-?\d+)', captured)
                    if statuses != [(kind.encode(), str(code).encode())]:
                        raise AssertionError(f'{name}: expected status {expected_status}; output={captured!r}')
                    position = 0
                    for marker in markers:
                        found = captured.find(marker.encode(), position)
                        if found < 0:
                            raise AssertionError(f'{name}: missing ordered marker {marker!r}; output={captured!r}')
                        position = found + len(marker)
                    if name.startswith('g3_exit_') and name not in ('g3_exit_abi', 'g3_exit_fault', 'g3_exit_abandon'):
                        for marker in markers:
                            if captured.count(marker.encode()) != 1:
                                raise AssertionError(f'{name}: repeated callback or marker: {marker!r}')
                    if name == 'g3_active_exit' and b'G3-X pending bytes must not be reported flushed' in captured:
                        raise AssertionError('blocked stdout flush was incorrectly reported complete')
                    if name == 'g3_exit_quick' and (b'G3-X quick pending stdout' in captured
                                                   or b'G3-X callback first once' in captured):
                        raise AssertionError('quick_exit flushed stdout or ran ordinary exit callbacks')
                    pump(guest, 0.1)
                    after = resources(guest)
                    if after != baseline:
                        raise AssertionError(f'{name}: resource drift {baseline} -> {after}')
                    report['runs'].append({'case': name, 'repetition': repetition + 1,
                                           'status': 'passed', 'expected_exit_code': code,
                                           'expected_outcome': kind, 'elapsed_seconds': elapsed,
                                           'resources': after, 'output': captured.decode(errors='replace')})
                    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            if args.suite in ('files', 'all'):
                if death_build:
                    report['runs'].append(service_death(death_build, programs['g3_files_single'],
                                                        output, report))
                else:
                    report['service_death'] = {
                        'status': 'not_run',
                        'reason': 'requires a separate --glibc-files-death-probe system build'}
            verify_inputs()
            for name, binary in programs.items():
                if sha(binary) != report['elfs'][name]['elf_sha256']:
                    raise RuntimeError('probe changed during qualification: ' + name)
            if dash is not None:
                if sha(dash) != report['dash_binding']['elf_sha256']:
                    raise RuntimeError('dash changed during qualification')
                report['dash_entry'] = 'passed'
            report['status'] = 'passed_subset'
    except (Exception, SystemExit) as error:
        report['error'] = str(error)
        raise
    finally:
        if guest:
            guest.close()
            (output / 'serial.log').write_bytes(guest.output)
            report['serial_sha256'] = sha(output / 'serial.log')
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: static glibc', args.suite, 'public APIs, exact exits and resource recovery')


if __name__ == '__main__':
    main()
