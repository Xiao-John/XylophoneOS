#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the freestanding XOS thread bridge in a real, privately booted guest."""
import hashlib
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / 'scripts'), str(root / 'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from work_disk import transfer


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    build = root/'build'
    overlay = root/'src/ports/glibc/sysdeps/xos'
    fixture = root/'tests/fixtures/glibc_g1'
    image = build/'xos-install.iso'
    system_manifest = build/'manifest.json'
    system = json.loads(system_manifest.read_text())
    def check_system():
        assert sha(system_manifest) == system_digest
        assert sha(image) == system['artifacts']['xos-install.iso']['sha256']
        for name, expected in system['sources'].items():
            assert sha(root/name) == expected, name
    system_digest = sha(system_manifest)
    check_system()
    probe = build/'glibc_g1_bridge_guest.elf'
    sources = [fixture/'thread_bridge_guest.c', fixture/'thread_bridge_guest.ld',
               overlay/'xos_thread_create.c', overlay/'xos_thread_create.h', overlay/'xos_wait_word.h', Path(__file__).resolve()]
    inputs = {str(path.relative_to(root)): sha(path) for path in sources}
    compiler = Path(shutil.which('x86_64-elf-gcc')).resolve(strict=True)
    cmd = [str(compiler), '-std=c11', '-O2', '-mno-red-zone', '-fno-pie', '-fno-pic',
           '-fno-stack-protector', '-ffreestanding', '-nostdlib', '-static', '-no-pie',
           '-Wl,--build-id=none', '-T', str(sources[1]), '-I', str(overlay),
           str(sources[0]), str(sources[2]), '-o', str(probe)]
    subprocess.run(cmd, check=True)
    assert inputs == {str(path.relative_to(root)): sha(path) for path in sources}
    report = {'status': 'failed', 'scope': 'freestanding XOS thread bridge; no glibc linked',
              'build_id': system['build_id'], 'system_manifest_sha256': sha(system_manifest),
              'image_sha256': sha(image), 'probe_sha256': sha(probe), 'inputs': inputs,
              'compiler_command': cmd, 'compiler_sha256': sha(compiler), 'checks': []}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_glibc_bridge_') as folder:
            disk = Path(folder)/'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/g1bridge', probe)
            guest = Guest(image, 'glibc_g1_bridge', iso=True, work_disk=disk)
            guest.expect(b'xos64> ', timeout=30)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=30)
            pump(guest, 1.5)
            before = resources(guest)
            outputs = []
            for _ in range(4):
                output = command(guest, 'exec-file /bin/g1bridge', b'kind=exited code=', timeout=90)
                if b'kind=exited code=0' not in output:
                    raise AssertionError(output[-3000:])
                after = resources(guest)
                if before != after:
                    raise AssertionError(f'resources differ: {before} -> {after}')
                outputs.append(output.decode(errors='replace'))
            check_system()
            assert inputs == {str(path.relative_to(root)): sha(path) for path in sources}
            assert sha(probe) == report['probe_sha256'] and sha(compiler) == report['compiler_sha256']
            report['checks'] = ['start_failure_rollback', 'prepare_start_native_traps',
                                'child_tls_and_exit', 'join_value', 'four_runs_resources_restored']
            report['resources'] = before
            report['output'] = outputs
            report['status'] = 'passed_subset'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        if guest is not None:
            guest.close()
        (build/'glibc_g1_bridge_guest_report.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS freestanding XOS thread bridge guest subset')

if __name__ == '__main__':
    main()
