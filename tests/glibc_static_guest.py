#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify the complete static XOS glibc SDK through public APIs in QEMU."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_glibc_sdk import inputs as glibc_inputs
from dash_c3_exec_smoke import exec_opt_in
from make_work_disk import create_fat32
from process_smoke import command, resources
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
             ['G3-T BEGIN active worker owns stdout', 'XOS glibc: exit with active threads']),
        ])
    if suite in ('files', 'all'):
        cases.extend([
            ('g3_files_single', 'glibc_g3/files_public_probe.c', ['single'], 0,
             ['GLIBC_G3_FILES_PASS', 'threaded=0']),
            ('g3_files_threads', 'glibc_g3/files_public_probe.c', [], 0,
             ['GLIBC_G3_FILES_PASS', 'threaded=1']),
        ])
    return cases


def build_newlib_parent(system_build, output, report):
    """Use the same system's existing SDK for an actual cross-libc exec."""
    sdk = system_build / 'sdk'
    receipt = json.loads((sdk / 'manifest.json').read_text())
    if receipt['build_id'] != report['system_build_id']:
        raise RuntimeError('newlib parent SDK and system build IDs differ')
    compiler = Path(shutil.which('x86_64-elf-gcc')).resolve(strict=True)
    libgcc = Path(subprocess.check_output([compiler, '-print-libgcc-file-name'], text=True).strip())
    headers = subprocess.check_output([compiler, '-print-file-name=include'], text=True).strip()
    source = ROOT / 'tests/fixtures/glibc_g3/files_exec_parent.c'
    binary = output / 'g3_files_parent.elf'
    obj = output / 'g3_files_parent.o'
    inputs = [sdk / name for name in ('crt0_posix.o', 'user.ld', 'lib/libxos.a',
              'lib/libxos_loader.a', 'lib/libc.a', 'lib/libm.a')]
    report['newlib_parent_inputs'] = {str(path.relative_to(sdk)): sha(path) for path in inputs}
    report['newlib_parent_libgcc_sha256'] = sha(libgcc)
    commands = [[str(compiler), '-std=gnu11', '-O2', '-g', '-mno-red-zone',
                 '-fno-pie', '-fno-pic', '-fno-stack-protector', '-nostdinc',
                 '-isystem', str(sdk / 'include'), '-isystem', headers,
                 '-c', str(source), '-o', str(obj)],
                [str(compiler), '-nostdlib', '-static', '-no-pie',
                 '-Wl,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
                 '-T', str(sdk / 'user.ld'), str(sdk / 'crt0_posix.o'), str(obj),
                 '-Wl,--start-group', *map(str, inputs[2:]), str(libgcc),
                 '-Wl,--end-group', '-o', str(binary)]]
    with (output / 'g3_files_parent_build.log').open('w') as log:
        for invocation in commands:
            subprocess.run(invocation, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    for path in inputs:
        if sha(path) != report['newlib_parent_inputs'][str(path.relative_to(sdk))]:
            raise RuntimeError('newlib SDK changed while building exec parent')
    report['elfs']['g3_files_parent'] = {'source': 'glibc_g3/files_exec_parent.c',
        'source_sha256': sha(source), 'elf_sha256': sha(binary), 'build_commands': commands,
        'compiler_sha256': sha(compiler), 'exec_receiver_marker': exec_opt_in(binary)}
    return binary


def service_death(guest, baseline):
    """Kill only the observed files service in the disposable guest."""
    listing = command(guest, 'ps', b'name=files ')
    matches = re.findall(rb'^pid=(\d+) name=files state=[^\n]+$', listing, re.MULTILINE)
    if len(matches) != 1:
        raise AssertionError('expected one live files service: ' + repr(listing))
    files_pid = int(matches[0])
    start = len(guest.output)
    spawned = command(guest, 'spawn-file /bin/g3_files_single service-death',
                      b'GLIBC_G3_FILES_DEATH_READY', timeout=30)
    children = re.findall(rb'\[loader\] started pid=(\d+)', spawned)
    if len(children) != 1:
        raise AssertionError('could not identify service-death probe')
    child = int(children[0])
    if child == files_pid:
        raise AssertionError('probe and files service identities overlap')
    command(guest, 'kill ' + str(files_pid), b'kill: accepted')
    waited = command(guest, 'wait ' + str(child), b'kind=exited code=', timeout=60)
    if re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', waited) != [b'0']:
        raise AssertionError('service-death probe failed: ' + repr(waited))
    captured = bytes(guest.output)[start:]
    if b'GLIBC_G3_FILES_DEATH_PASS' not in captured:
        raise AssertionError('service-death completion marker missing')
    after = resources(guest)
    if after[1] != baseline[1] - 1 or after[0] < baseline[0]:
        raise AssertionError('files-service death leaked a task or pages')
    return {'case': 'g3_files_service_death', 'status': 'passed',
            'files_pid': files_pid, 'probe_pid': child,
            'resources_after_service_removed': after,
            'output': captured.decode(errors='replace')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-build', type=Path, required=True)
    parser.add_argument('--glibc-build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--suite', choices=('g2', 'threads', 'files', 'all'), default='g2')
    parser.add_argument('--repetitions', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 10:
        parser.error('repetitions must be in 1..10')
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        parser.error('output must be a new private directory')
    output.mkdir(parents=True)
    report = {'status': 'not_run', 'suite': args.suite, 'runs': [],
              'qmp': 'disabled; serial-only qualification',
              'active_worker_normal_exit': 'unsupported; separate fail-fast status-127 check',
              'dash_entry': 'not_run'}
    guest = None
    try:
        system_build = args.system_build.resolve(strict=True)
        glibc_build = args.glibc_build.resolve(strict=True)
        system_manifest = system_build / 'manifest.json'
        glibc_manifest = glibc_build / 'manifest.json'
        system = json.loads(system_manifest.read_text())
        sdk = json.loads(glibc_manifest.read_text())
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

        verify_inputs()
        cases = suite_cases(args.suite)
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
        verify_inputs()
        report['status'] = 'failed'
        with tempfile.TemporaryDirectory(prefix='xos_glibc_static_') as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
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
            if args.suite in ('g2', 'all'):
                captured = command(guest, 'exec libc_hello', b'kind=exited code=', timeout=30)
                if b'libc says: malloc+printf 42 beef' not in captured or b'kind=exited code=7' not in captured:
                    raise AssertionError('newlib control failed: ' + repr(captured))
                if resources(guest) != baseline:
                    raise AssertionError('newlib control did not restore resources')
                report['newlib_control'] = 'passed: current-system malloc/printf/exit/resources'
            for repetition in range(args.repetitions):
                for name, _, arguments, expected_status, markers in cases:
                    launch = 'exec-driver' if name == 'g3_files_parent' else 'exec-file'
                    line = launch + ' /bin/' + name + ''.join(' ' + arg for arg in arguments)
                    captured = command(guest, line, b'kind=exited code=', timeout=120)
                    statuses = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', captured)
                    if statuses != [str(expected_status).encode()]:
                        raise AssertionError(f'{name}: expected status {expected_status}; output={captured!r}')
                    position = 0
                    for marker in markers:
                        found = captured.find(marker.encode(), position)
                        if found < 0:
                            raise AssertionError(f'{name}: missing ordered marker {marker!r}; output={captured!r}')
                        position = found + len(marker)
                    pump(guest, 0.1)
                    after = resources(guest)
                    if after != baseline:
                        raise AssertionError(f'{name}: resource drift {baseline} -> {after}')
                    report['runs'].append({'case': name, 'repetition': repetition + 1,
                                           'status': 'passed', 'expected_exit_code': expected_status,
                                           'resources': after, 'output': captured.decode(errors='replace')})
                    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            if args.suite in ('files', 'all'):
                report['runs'].append(service_death(guest, baseline))
            verify_inputs()
            for name, binary in programs.items():
                if sha(binary) != report['elfs'][name]['elf_sha256']:
                    raise RuntimeError('probe changed during qualification: ' + name)
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
