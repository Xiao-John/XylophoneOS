#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real holder-local release, pinned/fragment preflight, budgets and peer exit."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_smoke import Guest
from glibc_static_guest import system_sources
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from toolchain import tool
from work_disk import transfer
from xos_app import tree_receipt

CASES = ('features', 'quota', 'fragments', 'pinned', 'foreign',
         'owner_first', 'holder_first', 'holder_exit', 'owner_exit')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runs', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.runs <= 3:
        parser.error('runs must be in 1..3')
    system, out = args.system.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'runner_sha256': sha(Path(__file__)), 'cases': [],
              'scope': 'native SDK without libc; actual sys88 action24 and sys87 budget accounting',
              'not_covered': ['multicore shootdown', 'allocation fault injection', 'VM-continuation target race']}
    guest = None
    try:
        manifest = json.loads((system / 'manifest.json').read_text())
        if manifest['sources'] != system_sources():
            raise ValueError('system source mismatch')
        for name, entry in manifest['artifacts'].items():
            if sha(system / name) != entry['sha256']:
                raise ValueError('system artifact mismatch: ' + name)
        sdk = system / 'sdk'
        source = ROOT / 'tests/fixtures/ipc_v1_grant/release_probe.cpp'
        core = system / 'threading_core/libxos_thread_core.a'
        binary = out / 'grant_release.elf'
        command_line = [tool('g++'), '-std=c++17', '-Os', '-g', '-Wall', '-Wextra', '-Werror',
                        '-ffreestanding', '-fno-exceptions', '-fno-rtti', '-fno-stack-protector',
                        '-fno-pie', '-fno-pic', '-mno-red-zone', '-mgeneral-regs-only', '-nostdinc++',
                        '-ffunction-sections', '-fdata-sections', '-I', str(sdk / 'include'),
                        '-I', str(ROOT / 'src/user/include'), str(source), '-nostdlib', '-static', '-no-pie',
                        '-Wl,--gc-sections,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
                        '-T', str(sdk / 'user.ld'), str(sdk / 'crt0.o'), '-Wl,--start-group', str(core),
                        str(sdk / 'lib/libxos.a'), str(sdk / 'lib/libxos_loader.a'), '-Wl,--end-group', '-o', str(binary)]
        subprocess.run(command_line, check=True)
        subprocess.run([tool('objcopy'), '--strip-debug', str(binary)], check=True)
        if binary.stat().st_size > 131072:
            raise ValueError('probe exceeds ordinary native loader limit')
        report.update(build_id=manifest['build_id'], system_manifest_sha256=sha(system / 'manifest.json'),
                      sdk_tree_sha256=tree_receipt(sdk)[0], source_sha256=sha(source), elf_sha256=sha(binary),
                      thread_core_sha256=sha(core), thread_header_sha256=sha(ROOT / 'src/user/include/xos/thread_core.hpp'),
                      compile_command=command_line, image_sha256=sha(system / 'xos-install.iso'))
        with tempfile.TemporaryDirectory(prefix='xos_grant_release_') as folder:
            disk = Path(folder) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/grant_release.elf', binary)
            guest = Guest(system / 'xos-install.iso', 'grant_release', work_disk=disk,
                          network=True, qmp_enabled=False, log_dir=out)
            report['qemu_command'] = guest.command
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=60)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, 'demo quiet', b'demo tasks')
            command(guest, 'audio stop', b'audio: service stopped')
            command(guest, 'net-stop', b'kind=exited code=0', timeout=60)
            baseline = resources(guest)
            report['resources_before'] = baseline
            for iteration in range(args.runs):
                for case in CASES:
                    begin = len(guest.output)
                    text = command(guest, 'exec-driver /bin/grant_release.elf ' + case,
                                   b'kind=exited code=', timeout=35)
                    if b'kind=exited code=0' not in text or b'GRANT_RELEASE_FAIL' in text:
                        raise AssertionError('grant target failed: ' + text.decode(errors='replace'))
                    if case == 'owner_exit':
                        child = int(re.search(rb'GRANT_RELEASE_CHILD pid=(\d+)', text)[1])
                        guest.expect(b'GRANT_RELEASE_OWNER_EXIT_CHILD_PASS', start=begin, timeout=15)
                        # The grandchild is orphaned when its owner exits and
                        # auto-reaped; it is not an owned wait target of Xsh.
                        guest.expect(f'[task] event=reclaimed pid={child} pages='.encode(), start=begin, timeout=15)
                    elif b'GRANT_RELEASE_PASS ' + case.encode() not in text:
                        raise AssertionError('missing target case marker: ' + case)
                    after = resources(guest)
                    for _ in range(10):
                        if after == baseline:
                            break
                        pump(guest, 0.1)
                        after = resources(guest)
                    if after != baseline:
                        raise AssertionError(f'resource drift after {case}: {after} != {baseline}')
                    report['cases'].append({'iteration': iteration, 'name': case, 'resources_after': after})
            report['resources_after'] = resources(guest)
        if manifest['sources'] != system_sources():
            raise AssertionError('source changed during qualification')
        report['status'] = 'passed_holder_release_subset'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        if guest is not None:
            guest.close()
            report['serial_sha256'] = sha(out / 'grant_release_serial.log')
        (out / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(report['status'])


if __name__ == '__main__':
    main()
