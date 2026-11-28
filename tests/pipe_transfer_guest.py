#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify native pipe grants and packaged glibc spawn/exec against the matching kernel."""
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
from build_pipe_transfer_probe import INPUTS as native_inputs
from xos_app import tree_receipt
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
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output must be new')
    args.output.mkdir(parents=True)
    out = args.output.resolve()
    system_build, system_source = args.system_build.resolve(), args.system_source.resolve()
    sdk_build = args.sdk_build.resolve()
    system_path, sdk_path = system_build / 'manifest.json', sdk_build / 'manifest.json'
    system, sdk = json.loads(system_path.read_text()), json.loads(sdk_path.read_text())
    report = {'status': 'failed', 'suite': 'p1-k5-pipes', 'runs': [],
              'system_build_id': system['build_id'], 'system_manifest_sha256': sha(system_path),
              'sdk_manifest_sha256': sha(sdk_path), 'runner_sha256': sha(__file__),
              'image_sha256': sha(system_build / 'xos-install.iso'),
              'system_source_distinct_from_sdk_source': system_source != ROOT,
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
                  '--id', 'xos-x86_64-glibc-p1-k5-pipes', '--feature', 'stdio_transfer', '--output', profile])
        run_build('dash', [sys.executable, ROOT / 'scripts/build_dash.py',
                  '--sdk', sdk_build / 'sysroot', '--glibc-profile', profile,
                  '--receipt', out / 'dash.json'])
        dash = json.loads((out / 'dash.json').read_text())
        dash_binary = ROOT / dash['elf']
        assert sha(dash_binary) == dash['sha256']
        report['dash'] = {'elf_sha256': sha(dash_binary), 'receipt_sha256': sha(out / 'dash.json'),
                          'sdk_manifest_sha256': dash['sdk_manifest_sha256']}
        report['profile_sha256'] = sha(profile)
        run_build('native', [sys.executable, ROOT / 'scripts/build_pipe_transfer_probe.py',
                  '--sdk', system_build / 'sdk', '--output', out / 'native'])
        native = json.loads((out / 'native/receipt.json').read_text())
        assert native['status'] == 'built_not_run' and not native['libc_linked']
        assert native['sdk_tree_sha256'] == tree_receipt(system_build / 'sdk')[0]
        assert native['sources'] == {path: sha(ROOT / path) for path in native_inputs}
        report['native'] = {'receipt_sha256': sha(out / 'native/receipt.json'),
                            'sdk_tree_sha256': native['sdk_tree_sha256'],
                            'sources': native['sources'], 'artifacts': native['artifacts']}
        cases = [
            ('spawn_pipe', 'glibc_g3/spawn_pipe_routes.c', '', [
                'SPAWN_PIPE_PASS routed_read_write_alias_flags_cloexec_eof_before_exit',
                'SPAWN_PIPE_PASS kernel_extra_alias_after_original_stdio_close',
                'SPAWN_PIPE_PASS independent_pipe_transfer_parent_preserved',
                'SPAWN_PIPE_PASS closed_reader_epipe', 'SPAWN_PIPE_OK cases=4']),
            ('independent_pipes', 'glibc_g3/independent_pipes.c', '', [
                'INDEPENDENT_PIPE_PASS independent_alias_flags_cloexec_eof_before_exit',
                'INDEPENDENT_PIPE_PASS same_pid_exec',
                'INDEPENDENT_PIPE_PASS failed_and_successful_exec_parent_preserved',
                'INDEPENDENT_PIPE_PASS independent_reader_close_epipe',
                'INDEPENDENT_PIPE_PASS eight_objects_sixteen_references_thirtytwo_descriptors',
                'INDEPENDENT_PIPE_OK cases=4']),
        ]
        for name, source, _, _ in cases:
            binary = out / (name + '.elf')
            run_build(name, [sys.executable, ROOT / 'scripts/build_glibc_program.py',
                      '--sdk', sdk_build / 'sysroot', '--profile', profile, '--stdio-transfer',
                      '--source', ROOT / 'tests/fixtures' / source, '--output', binary])
            report['programs'][name] = {'source': source, 'source_sha256': sha(ROOT / 'tests/fixtures' / source),
                                         'elf_sha256': sha(binary)}
        verify()
        disk = out / 'work.img'
        create_fat32(disk, 512)
        for path in ('/bin', '/tests', '/data'):
            transfer(disk, 'mkdir', path)
        transfer(disk, 'import', '/bin/dash', dash_binary)
        transfer(disk, 'import', '/bin/pipe_transfer.elf', out / 'native/pipe_transfer.elf')
        for name, _, arguments, _ in cases:
            transfer(disk, 'import', '/bin/' + name, out / (name + '.elf'))
            script = out / (name + '.sh')
            script.write_text('/bin/' + name + arguments
                              + '\nrc=$?\nprintf "K5_PIPE_DASH_RC=%s\\n" "$rc"\nexit "$rc"\n')
            transfer(disk, 'import', '/tests/' + name + '.sh', script)
        guest = Guest(system_build / 'xos-install.iso', 'k5_pipe_transfer', work_disk=disk,
                      iso=True, qmp_enabled=False, log_dir=out)
        report['qemu_command'] = guest.command
        report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
        guest.expect(b'xos64> ', timeout=30)
        send_bytes(guest, b'run\r')
        guest.expect_supervisor(trace=True, timeout=30)
        command(guest, 'demo quiet', b'demo tasks')
        command(guest, 'audio stop', b'xsh> ')
        pump(guest, 0.2)
        baseline = resources(guest)
        report['baseline'] = baseline
        save()
        for number in range(2):
            for mode in ('invalid', 'readonly', 'pending', 'capacity', 'loader', 'positive'):
                captured = command(guest, 'exec-driver /bin/pipe_transfer.elf ' + mode,
                                   b'kind=exited code=', timeout=90)
                assert ('PIPE_TRANSFER_PASS ' + mode).encode() in captured and b'PIPE_TRANSFER_FAIL' not in captured, captured[-6000:]
                assert re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', captured) == [b'0'], captured[-6000:]
                pump(guest, 0.2)
                after = resources(guest)
                assert after == baseline, (mode, baseline, after)
                report['runs'].append({'program': 'native', 'case': mode, 'round': number,
                                        'status': 'passed', 'resources': after,
                                        'output': captured.decode(errors='replace')})
                save(); print('PASS native', mode, number, flush=True)
        for shell in ('xsh', 'dash'):
            for name, _, arguments, markers in cases:
                line = '/bin/' + name + arguments if shell == 'xsh' else '/bin/dash /tests/' + name + '.sh'
                captured = command(guest, line, b'kind=exited code=', timeout=120)
                statuses = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', captured)
                assert statuses == [b'0'], (name, shell, captured[-6000:])
                for marker in markers:
                    assert marker.encode() in captured, (name, marker, captured[-6000:])
                if shell == 'dash':
                    assert b'K5_PIPE_DASH_RC=0' in captured
                pump(guest, 0.1)
                after = resources(guest)
                assert after == baseline, (name, baseline, after)
                report['runs'].append({'program': name, 'shell': shell, 'status': 'passed',
                                        'resources': after, 'output': captured.decode(errors='replace')})
                save()
                print('PASS', name, shell, flush=True)
        verify()
        assert native['sources'] == {path: sha(ROOT / path) for path in native_inputs}
        assert native['sdk_tree_sha256'] == tree_receipt(system_build / 'sdk')[0]
        for name, digest in native['artifacts'].items():
            assert sha(out / 'native' / name) == digest
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
