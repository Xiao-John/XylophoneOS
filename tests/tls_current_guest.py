#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise sys35 explicit current-thread installation in a fresh XOS guest."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from work_disk import transfer


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {'status': 'not_run', 'checks': []}
    guest = None
    try:
        build = args.system_build.resolve(strict=True)
        manifest_path = build / 'manifest.json'
        system = json.loads(manifest_path.read_text())
        image = build / 'xos-install.iso'
        assert sha(image) == system['artifacts']['xos-install.iso']['sha256']
        for name, digest in system['sources'].items():
            assert sha(ROOT / name) == digest, f'system source changed: {name}'
        fixture = ROOT / 'tests/fixtures/tls_current'
        sources = [fixture / name for name in ('probe.cpp', 'entry.asm', 'probe.ld')]
        sources += [ROOT / 'src/shared/include/xos' / name
                    for name in ('abi_types.hpp', 'process_abi.hpp', 'thread_abi.hpp')]
        sources.append(Path(__file__).resolve())
        report.update({'build_id': system['build_id'], 'image_sha256': sha(image),
                       'system_manifest_sha256': sha(manifest_path),
                       'sources': {str(path.relative_to(ROOT)): sha(path) for path in sources}})
        compiler = Path(shutil.which('x86_64-elf-g++')).resolve(strict=True)
        nasm = Path(shutil.which('nasm')).resolve(strict=True)
        report['compiler'] = {'sha256': sha(compiler),
                              'version': subprocess.check_output([compiler, '--version'], text=True).splitlines()[0]}
        probe = output / 'tls_current.elf'
        entry = output / 'entry.o'
        commands = [[str(nasm), '-f', 'elf64', str(fixture / 'entry.asm'), '-o', str(entry)],
                    [str(compiler), '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror',
                     '-Wconversion', '-Wshadow', '-ffreestanding', '-fno-exceptions', '-fno-rtti',
                     '-mno-red-zone', '-mgeneral-regs-only', '-fno-stack-protector', '-fno-pie', '-fno-pic',
                     '-nostdinc++', '-nostdlib', '-static', '-no-pie', '-Wl,--build-id=none,-z,noexecstack',
                     '-I', str(ROOT / 'src/shared/include'), '-T', str(fixture / 'probe.ld'),
                     str(fixture / 'probe.cpp'), str(entry), '-o', str(probe)]]
        for invocation in commands:
            subprocess.run(invocation, check=True)
        report['commands'] = commands
        report['elf_sha256'] = sha(probe)
        report['status'] = 'failed'
        with tempfile.TemporaryDirectory(prefix='xos_tls_current_') as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/tls_current', probe)
            guest = Guest(image, 'tls_current', work_disk=disk, iso=True, qmp_enabled=False)
            report['qemu_command'] = guest.command
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=30)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=30)
            command(guest, 'demo quiet', b'demo tasks')
            baseline = resources(guest)
            report['baseline'] = baseline
            for attempt in range(3):
                captured = command(guest, 'exec-driver /bin/tls_current', b'kind=exited code=', timeout=30)
                assert b'[tls-current] result=pass' in captured, captured
                assert b'kind=exited code=0' in captured, captured
                pump(guest, 0.1)
                assert resources(guest) == baseline
                report['checks'].append(f'launch_{attempt + 1}_checks_and_exact_resource_recovery')
            report['status'] = 'passed'
    except (Exception, SystemExit) as error:
        report['error'] = str(error)
        raise
    finally:
        if guest:
            guest.close()
            (output / 'serial.log').write_bytes(guest.output)
            report['serial_sha256'] = sha(output / 'serial.log')
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: current-thread TLS control, negative cases, isolation, leaving and recovery')


if __name__ == '__main__':
    main()
