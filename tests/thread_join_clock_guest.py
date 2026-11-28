#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run actual public pthread joins and target CPU clocks on new/old kernels."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_glibc_sdk import inputs as sdk_inputs
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes
from work_disk import transfer


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-build', required=True, type=Path)
    parser.add_argument('--glibc-build', required=True, type=Path)
    parser.add_argument('--old-system-build', type=Path)
    parser.add_argument('--legacy-sdk', type=Path, help='separately rebuilt threaded newlib SDK')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--repetitions', type=int, default=3)
    args = parser.parse_args()
    if args.repetitions < 1 or args.repetitions > 20:
        parser.error('repetitions must be 1..20')
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    sdk = args.glibc_build.resolve(strict=True)
    sdk_manifest = json.loads((sdk / 'manifest.json').read_text())
    if sdk_manifest['status'] != 'static_sdk_built' or sdk_manifest['inputs'] != sdk_inputs():
        raise RuntimeError('SDK is incomplete or its source snapshot changed')
    for name, digest in sdk_manifest['artifacts'].items():
        if sha(sdk / 'sysroot' / name) != digest:
            raise RuntimeError('SDK artifact changed: ' + name)
    source = ROOT / 'tests/fixtures/glibc_g3/thread_join_clock.c'
    binary = output / 'thread_join_clock.elf'
    invocation = [sys.executable, str(ROOT / 'scripts/build_glibc_program.py'),
                  '--sdk', str(sdk / 'sysroot'), '--source', str(source), '--output', str(binary)]
    with (output / 'build.log').open('w') as log:
        subprocess.run(invocation, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    report = {'status': 'running', 'source_sha256': sha(source), 'runner_sha256': sha(__file__),
              'sdk_manifest_sha256': sha(sdk / 'manifest.json'), 'elf_sha256': sha(binary),
              'build_command': invocation, 'runs': [], 'systems': {}}
    legacy_binary = None
    if args.legacy_sdk:
        legacy = args.legacy_sdk.resolve(strict=True)
        manifest = json.loads((legacy / 'manifest.json').read_text())
        if manifest.get('profile') != 'xos-threading-v1-experimental':
            raise RuntimeError('requires the separate multithread newlib SDK')
        for name, digest in manifest['artifacts'].items():
            if sha(legacy / name) != digest:
                raise RuntimeError('legacy SDK artifact changed: ' + name)
        compiler = shutil.which('x86_64-elf-gcc')
        builtin = subprocess.check_output([compiler, '-print-file-name=include'], text=True).strip()
        libgcc = subprocess.check_output([compiler, '-print-libgcc-file-name'], text=True).strip()
        legacy_binary = output / 'thread_join_clock_legacy.elf'
        invocation = [compiler, '-std=c11', '-O2', '-g', '-mno-red-zone', '-fno-pie', '-fno-pic',
                      '-fno-stack-protector', '-DXOS_THREADED_RUNTIME', '-nostdinc',
                      '-isystem', str(legacy / 'include'), '-isystem', builtin,
                      '-nostdlib', '-static', '-no-pie', '-T', str(legacy / 'user.ld'),
                      str(legacy / 'crt0_posix.o'), str(source), '-Wl,--start-group',
                      str(legacy / 'lib/libxos.a'), str(legacy / 'lib/libc.a'),
                      str(legacy / 'lib/libm.a'), libgcc, '-Wl,--end-group', '-o', str(legacy_binary)]
        with (output / 'legacy_build.log').open('w') as log:
            subprocess.run(invocation, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        report['legacy'] = {'manifest_sha256': sha(legacy / 'manifest.json'),
                            'elf_sha256': sha(legacy_binary), 'compiler_sha256': sha(compiler),
                            'libgcc_sha256': sha(libgcc), 'build_command': invocation}
    try:
        systems = [('current', args.system_build, args.repetitions)]
        if args.old_system_build:
            systems.append(('old', args.old_system_build, 1))
        for name, path, repetitions in systems:
            path = path.resolve(strict=True)
            system = json.loads((path / 'manifest.json').read_text())
            for relative, record in system['artifacts'].items():
                if sha(path / relative) != record['sha256']:
                    raise RuntimeError('system artifact changed: ' + relative)
            if name == 'current':
                for relative, digest in system['sources'].items():
                    if sha(ROOT / relative) != digest:
                        raise RuntimeError('system input changed: ' + relative)
            report['systems'][name] = {'build_id': system['build_id'],
                                       'manifest_sha256': sha(path / 'manifest.json'),
                                       'iso_sha256': sha(path / 'xos-install.iso')}
            with tempfile.TemporaryDirectory(prefix='xos_join_clock_') as temporary:
                disk = Path(temporary) / 'work.img'
                create_fat32(disk, 512)
                transfer(disk, 'mkdir', '/bin')
                transfer(disk, 'import', '/bin/join_clock', binary)
                if legacy_binary and name == 'current':
                    transfer(disk, 'import', '/bin/join_clock_legacy', legacy_binary)
                guest = Guest(path / 'xos-install.iso', 'thread_join_clock_' + name,
                              work_disk=disk, iso=True, qmp_enabled=False)
                try:
                    guest.expect(b'xos64> ', timeout=30)
                    send_bytes(guest, b'run\r')
                    guest.expect_supervisor(trace=True, timeout=30)
                    command(guest, 'demo quiet', b'demo tasks')
                    baseline = resources(guest)
                    report['systems'][name]['baseline'] = baseline
                    report['systems'][name]['qemu_command'] = guest.command
                    report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
                    cases = [('glibc', 'join_clock', repetitions)]
                    if legacy_binary and name == 'current':
                        cases.append(('newlib', 'join_clock_legacy', repetitions))
                    for libc, program, count in cases:
                        for repetition in range(count):
                            # The current case checks a forked child's authority.
                            line = 'exec-driver /bin/' + program + (' old-kernel' if name == 'old' else '')
                            captured = command(guest, line, b'kind=exited code=', timeout=90)
                            (output / f'{name}_{libc}_{repetition + 1}.log').write_bytes(captured)
                            markers = ['old_kernel_explicit_rejection_legacy_join'] if name == 'old' else [
                                'tryjoin_deadline_timeout_output_preserved',
                                'target_cpu_identity_sleep_busy_resolution', 'versioned_abi_invalid_requests',
                                'join_detach_contention_timeout_release_stale_clock',
                                'detached_cpu_clock_lifecycle', 'lifecycle_reuse_and_complete']
                            if name == 'current' and libc == 'glibc':
                                markers.append('cross_process_cpu_query_rejected')
                            if b'kind=exited code=0' not in captured or any(
                                    ('ISSUE125_PASS ' + marker).encode() not in captured for marker in markers):
                                raise AssertionError(captured.decode(errors='replace'))
                            after = resources(guest)
                            if after != baseline:
                                raise AssertionError(f'resource drift: {baseline} -> {after}')
                            report['runs'].append({'system': name, 'libc': libc, 'repetition': repetition + 1,
                                                   'markers': markers, 'exit_code': 0, 'resources': after})
                finally:
                    guest.close()
        report['status'] = 'passed'
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        raise
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
