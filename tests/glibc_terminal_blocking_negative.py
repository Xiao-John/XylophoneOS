#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prove the terminal guest gate rejects a real read that holds the files lock."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'scripts')]
from boot_smoke import Guest
from glibc_terminal_guest import glibc_inputs, release_blocked_reader, sha, system_sources, tty_opt_in
from terminal_observation_sector import prepare_observations
from make_work_disk import create_fat32
from process_smoke import command
from task_smoke import send_bytes
from work_disk import transfer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-build', type=Path, required=True)
    parser.add_argument('--glibc-build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    guest = None
    report = {'status': 'failed', 'scope': 'fault-injected diagnostic ELF; SDK remains unchanged',
              'input_events': [], 'expected_failure': 'file progress cannot occur while the read retains the files lock'}
    try:
        system_build = args.system_build.resolve(strict=True)
        glibc_build = args.glibc_build.resolve(strict=True)
        system_path, sdk_path = system_build / 'manifest.json', glibc_build / 'manifest.json'
        system, sdk = json.loads(system_path.read_text()), json.loads(sdk_path.read_text())
        sysroot = glibc_build / 'sysroot'
        initial_system, initial_sdk = sha(system_path), sha(sdk_path)

        def verify():
            if initial_system != sha(system_path) or initial_sdk != sha(sdk_path):
                raise RuntimeError('input manifest changed')
            if system_sources() != system['sources'] or glibc_inputs() != sdk['inputs']:
                raise RuntimeError('source inputs changed')
            if sdk.get('status') != 'static_sdk_built':
                raise RuntimeError('complete static SDK required')
            for name, item in system['artifacts'].items():
                if sha(system_build / name) != item['sha256']:
                    raise RuntimeError('system artifact changed: ' + name)
            inventory = {str(path.relative_to(sysroot)): sha(path)
                         for path in sorted(sysroot.rglob('*')) if path.is_file()}
            if inventory != sdk['artifacts']:
                raise RuntimeError('SDK artifact inventory changed')

        verify()
        report.update(system_manifest_sha256=initial_system, sdk_manifest_sha256=initial_sdk,
                      system_build_id=system['build_id'], runner_sha256=sha(Path(__file__).resolve()),
                      gate_sha256=sha(ROOT / 'tests/glibc_terminal_guest.py'))
        overlay = ROOT / 'src/ports/glibc/sysdeps/xos'
        private = output / 'mutation'
        private.mkdir()
        for header in overlay.glob('*.h'):
            shutil.copyfile(header, private / header.name)
        runtime = overlay / 'xos_file_runtime.c'
        original = runtime.read_text()
        before = '''      unlock_session ();
      result = stream_io (copy, buffer, length, writing);
      /* A lease retains the actual route while another thread closes the FD. */
      error = lock_session ();'''
        after = '''      /* Fault injection only: retain the files lock across terminal read. */
      const int hold_file_lock = copy.kind == kind_terminal && !writing;
      if (!hold_file_lock) unlock_session ();
      result = stream_io (copy, buffer, length, writing);
      error = hold_file_lock ? 0 : lock_session ();'''
        if original.count(before) != 1:
            raise RuntimeError('expected runtime lease boundary not found exactly once')
        mutant = private / 'xos_file_runtime.c'
        mutant.write_text(original.replace(before, after))
        report['mutation'] = {'source': str(runtime.relative_to(ROOT)), 'original_sha256': sha(runtime),
                              'diagnostic_sha256': sha(mutant), 'before': before, 'after': after}
        binary = output / 'terminal_lock_fault.elf'
        call = [sys.executable, str(ROOT / 'scripts/build_glibc_program.py'), '--diagnostic',
                '--sdk', str(sysroot), '--source', str(ROOT / 'tests/fixtures/glibc_g3/terminal_public_probe.c'),
                '--source', str(mutant), '--output', str(binary)]
        with (output / 'program_build.log').open('w') as log:
            subprocess.run(call, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        report['program'] = {'command': call, 'elf_sha256': sha(binary), 'tty_marker': tty_opt_in(binary),
                             'manifest_sha256': sha(output / 'terminal_lock_fault.elf.build/manifest.json')}
        with tempfile.TemporaryDirectory(prefix='xos_terminal_lock_fault_') as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/terminal_lock_fault', binary)
            transfer(disk, 'import', '/bin/terminal.elf', system_build / 'user_terminal.image.elf')
            observation = prepare_observations(disk, 1)[0]
            report['observation'] = observation
            report['work_disk_initial_sha256'] = sha(disk)
            guest = Guest(system_build / 'xos-install.iso', 'glibc_terminal_lock_fault',
                          work_disk=disk, iso=True, qmp_enabled=False)
            report['qemu_command'] = guest.command
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=30)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=30)
            command(guest, 'demo quiet', b'demo tasks')
            start = len(guest.output)
            send_bytes(guest, ('tty-run /bin/terminal_lock_fault ' + observation['path'] + ' ' + observation['nonce'] + '\r').encode())
            guest.expect(b'GLIBC_TERMINAL_BLOCK_READY', start=start, timeout=60)
            # The deliberate lock bug prevents the complete progress record.
            # A deadline detects the failure; it never grants permission to
            # inject input without an exact fresh 512-byte record.
            try:
                release_blocked_reader(guest, start, report, 1, disk, observation, timeout=5)
            except AssertionError as error:
                captured = bytes(guest.output[start:])
                with disk.open('rb', buffering=0) as stream:
                    stream.seek(observation['offset'])
                    untouched = stream.read(512) == bytes(512)
                if (guest.process.poll() is not None or not untouched or b'kind=exited code=' in captured
                        or b'GLIBC_TERMINAL_FAIL' in captured or report['input_events']
                        or str(error) != 'blocked-reader file-progress record timed out; input withheld'):
                    raise RuntimeError('negative run failed outside the intended blocked-file gate') from error
                report['observed_failure'] = str(error)
                report['observation_sector_unchanged'] = True
                report['file_progress_timeout_seconds'] = 5
                report['input_bytes_after_launch'] = 0
            else:
                raise RuntimeError('faulty runtime passed the file-progress gate')
            verify()
            report['status'] = 'passed_negative_detection'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if guest is not None:
            guest.close()
            (output / 'serial.log').write_bytes(guest.output)
            report['serial_sha256'] = sha(output / 'serial.log')
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS negative detection: file-progress record timed out, sector unchanged, no early input')


if __name__ == '__main__':
    main()
