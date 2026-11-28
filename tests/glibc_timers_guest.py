#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify timer and self CPU clocks using a rebuilt SDK and a pinned kernel."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_glibc_sdk import inputs as sdk_inputs
from glibc_static_guest import system_sources
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from work_disk import transfer


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-build', type=Path, required=True)
    parser.add_argument('--system-source', type=Path, required=True)
    parser.add_argument('--sdk-build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--suite', choices=('self-clock', 'timers', 'all'), default='all')
    parser.add_argument('--native-sleep', action='store_true',
                        help='stage timer qualification using native waits; public nanosleep not qualified')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output must be new')
    args.output.mkdir(parents=True)
    out = args.output.resolve()
    system_build, system_source = args.system_build.resolve(), args.system_source.resolve()
    sdk_build = args.sdk_build.resolve()
    system_path, sdk_path = system_build / 'manifest.json', sdk_build / 'manifest.json'
    system, sdk = json.loads(system_path.read_text()), json.loads(sdk_path.read_text())
    report = {'status': 'failed', 'suite': args.suite, 'runs': [],
              'system_build_id': system['build_id'], 'system_manifest_sha256': sha(system_path),
              'sdk_manifest_sha256': sha(sdk_path), 'runner_sha256': sha(__file__),
              'image_sha256': sha(system_build / 'xos-install.iso'),
              'system_source_distinct_from_sdk_source': system_source != ROOT,
              'fixture_sleep': 'native sys47' if args.native_sleep else 'public nanosleep',
              'qmp': 'disabled; serial only', 'programs': {}}
    guest = None

    def save():
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    def verify():
        assert sdk['status'] == 'static_sdk_built'
        assert sha(system_path) == report['system_manifest_sha256']
        assert sha(sdk_path) == report['sdk_manifest_sha256']
        assert system_sources(system_source) == system['sources']
        assert sdk_inputs() == sdk['inputs']
        for name, item in system['artifacts'].items():
            assert sha(system_build / name) == item['sha256'], name
        for name, digest in sdk['artifacts'].items():
            assert sha(sdk_build / 'sysroot' / name) == digest, name

    def run_build(name, invocation):
        with (out / (name + '.log')).open('w') as log:
            subprocess.run(list(map(str, invocation)), cwd=ROOT, check=True,
                           stdout=log, stderr=subprocess.STDOUT)

    try:
        verify()
        profile = out / 'profile.json'
        run_build('profile', [sys.executable, ROOT / 'scripts/create_xypm_profile.py', 'create',
                  '--runtime-family', 'glibc', '--sdk-build', sdk_build,
                  '--id', 'xos-x86_64-glibc-issue124', '--feature', 'stdio_transfer', '--output', profile])
        run_build('dash', [sys.executable, ROOT / 'scripts/build_dash.py',
                  '--sdk', sdk_build / 'sysroot', '--glibc-profile', profile,
                  '--receipt', out / 'dash.json'])
        dash = json.loads((out / 'dash.json').read_text())
        dash_binary = ROOT / dash['elf']
        assert sha(dash_binary) == dash['sha256']
        report['dash'] = {'elf_sha256': sha(dash_binary), 'receipt_sha256': sha(out / 'dash.json'),
                          'sdk_manifest_sha256': dash['sdk_manifest_sha256']}
        report['profile_sha256'] = sha(profile)
        cases = []
        if args.suite in ('self-clock', 'all'):
            cases.append(('self_cpuclock', 'glibc_timers/self_cpuclock.c', '', ['SELF_CPUCLOCK_PASS']))
        if args.suite in ('timers', 'all'):
            cases += [
                ('timer_none', 'glibc_timers/timer_none.c', ' fork',
                 ['TIMER_NONE_PASS pool_32', 'TIMER_NONE_PASS periodic_phase',
                  'TIMER_NONE_PASS invalid_times', 'TIMER_NONE_PASS realtime_absolute',
                  'TIMER_NONE_PASS fork_child_reset', 'TIMER_NONE_PASS complete']),
                ('timer_thread', 'glibc_timers/timer_thread.c', '',
                 ['TIMER_THREAD_PASS scheduler_quota_failure',
                  'TIMER_THREAD_PASS rearm_wakes', 'TIMER_THREAD_PASS bounded_callback',
                  'TIMER_THREAD_PASS pthread_exit_TSD', 'TIMER_THREAD_PASS delete_reuse',
                  'TIMER_THREAD_PASS quota_retry', 'TIMER_THREAD_PASS explicit_stack',
                  'TIMER_THREAD_PASS complete']),
                ('thread_regression', 'glibc_g3/threads.c', '', ['G3-T PASS complete']),
                ('detach_regression', 'glibc_g3/detached_threads.c', '',
                 ['G3-T PASS detached creation detach TSD slots kernel-stack recovery rounds=16']),
            ]
        for name, source, _, _ in cases:
            binary = out / (name + '.elf')
            invocation = [sys.executable, ROOT / 'scripts/build_glibc_program.py',
                      '--sdk', sdk_build / 'sysroot', '--profile', profile, '--stdio-transfer',
                      '--source', ROOT / 'tests/fixtures' / source, '--output', binary]
            if args.native_sleep and name in ('timer_none', 'timer_thread'):
                invocation += ['--define', 'XOS_TIMER_NATIVE_SLEEP']
            run_build(name, invocation)
            report['programs'][name] = {'source': source, 'source_sha256': sha(ROOT / 'tests/fixtures' / source),
                                         'elf_sha256': sha(binary)}
        verify()
        disk = out / 'work.img'
        create_fat32(disk, 512)
        for path in ('/bin', '/tests'):
            transfer(disk, 'mkdir', path)
        transfer(disk, 'import', '/bin/dash', dash_binary)
        for name, _, arguments, _ in cases:
            transfer(disk, 'import', '/bin/' + name, out / (name + '.elf'))
            script = out / (name + '.sh')
            script.write_text('/bin/' + name + arguments
                              + '\nrc=$?\nprintf "ISSUE124_DASH_RC=%s\\n" "$rc"\nexit "$rc"\n')
            transfer(disk, 'import', '/tests/' + name + '.sh', script)
        guest = Guest(system_build / 'xos-install.iso', 'issue124', work_disk=disk,
                      iso=True, qmp_enabled=False, log_dir=out)
        report['qemu_command'] = guest.command
        report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
        guest.expect(b'xos64> ', timeout=30)
        send_bytes(guest, b'run\r')
        guest.expect_supervisor(trace=True, timeout=30)
        command(guest, 'demo quiet', b'demo tasks')
        baseline = resources(guest)
        report['baseline'] = baseline
        save()
        for shell in ('xsh', 'dash'):
            for name, _, arguments, markers in cases:
                line = '/bin/' + name + arguments if shell == 'xsh' else '/bin/dash /tests/' + name + '.sh'
                captured = command(guest, line, b'kind=exited code=', timeout=120)
                statuses = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', captured)
                assert statuses == [b'0'], (name, shell, captured[-6000:])
                for marker in markers:
                    assert marker.encode() in captured, (name, marker, captured[-6000:])
                if shell == 'dash':
                    assert b'ISSUE124_DASH_RC=0' in captured
                pump(guest, 0.1)
                after = resources(guest)
                assert after == baseline, (name, baseline, after)
                report['runs'].append({'program': name, 'shell': shell, 'status': 'passed',
                                        'resources': after, 'output': captured.decode(errors='replace')})
                save()
                print('PASS', name, shell, flush=True)
        verify()
        for name, item in report['programs'].items():
            assert sha(out / (name + '.elf')) == item['elf_sha256']
        assert sha(dash_binary) == report['dash']['elf_sha256']
        report['status'] = 'passed'
    finally:
        if guest:
            guest.close()
            (out / 'serial.log').write_bytes(guest.output)
            report['serial_sha256'] = sha(out / 'serial.log')
        save()
    print(json.dumps({'status': report['status'], 'runs': len(report['runs']),
                      'system_build_id': report['system_build_id']}))


if __name__ == '__main__':
    main()
