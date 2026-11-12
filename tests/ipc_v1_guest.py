#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build and run IPC v1 race/resource probes in an actual XOS guest.

This probes the IP2/IP3 behavior covered by the guest qualification record. It is
not a fastpath performance probe and does not establish any new feature support.
"""
import argparse
import hashlib
import json
import os
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
from toolchain import X86_FLAGS, tool
from work_disk import transfer


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--system', type=Path, required=True,
                        help='built XOS system directory containing xos-install.iso')
    parser.add_argument('--sdk', type=Path, default=ROOT / 'build/threading_sdk',
                        help='threading SDK built for the same source/toolchain')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runs', type=int, default=3)
    args = parser.parse_args()
    if args.runs < 1 or args.runs > 20:
        parser.error('--runs must be between 1 and 20')
    system, sdk = args.system.resolve(), args.sdk.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    image = system / 'xos-install.iso'
    manifest_path = system / 'manifest.json'
    sdk_manifest = sdk / 'manifest.json'
    for required in (image, manifest_path, sdk_manifest, sdk / 'crt0_posix.o',
                     sdk / 'user.ld', sdk / 'lib/libxos.a', sdk / 'lib/libc.a',
                     sdk / 'lib/libm.a', sdk / 'cpp/lib/libstdc++.a',
                     sdk / 'cpp/lib/libsupc++.a', sdk / 'cpp/lib/libgcc.a'):
        if not required.is_file():
            parser.error(f'missing required input: {required}')
    system_manifest = json.loads(manifest_path.read_text())
    sdk_data = json.loads(sdk_manifest.read_text())
    image_digest = digest(image)
    recorded_image = system_manifest.get('artifacts', {}).get('xos-install.iso', {}).get('sha256')
    if recorded_image != image_digest:
        parser.error('xos-install.iso hash does not match the system manifest')
    for artifact, expected in sdk_data.get('artifacts', {}).items():
        artifact_path = sdk / artifact
        if not artifact_path.is_file() or digest(artifact_path) != expected:
            parser.error(f'threading SDK artifact differs from manifest: {artifact}')
    env = os.environ.copy()
    tools_dir = sdk.parent / 'threading_probe_tools'
    if tools_dir.is_dir():
        env['COMPILER_PATH'] = str(tools_dir)
    source = ROOT / 'tests/fixtures/ipc_v1/ipc_v1_probe.cpp'
    obj, elf = output / 'ipc_v1_probe.o', output / 'ipc_v1_probe.elf'
    common = ['-std=c++20', '-O2', '-g', '-fno-pic', '-fno-pie', *X86_FLAGS,
              '-fno-stack-protector', '-fno-exceptions', '-fno-rtti',
              '-ftls-model=local-exec', '-D_POSIX_C_SOURCE=200809L',
              '-DXOS_THREADED_RUNTIME', '-I' + str(ROOT / 'src/user/include'),
              '-I' + str(ROOT / 'src/shared/include'), '-I' + str(sdk / 'cpp/include'),
              '-I' + str(sdk / 'cpp/include/x86_64-elf'), '-I' + str(sdk / 'include')]
    commands = []
    compile_cmd = [tool('g++'), *common, '-c', str(source), '-o', str(obj)]
    link_cmd = [tool('g++'), '-nostdlib', '-static', '-no-pie',
                '-Wl,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
                '-T', str(sdk / 'user.ld'), str(sdk / 'crt0_posix.o'), str(obj),
                '-Wl,--start-group', '-Wl,--whole-archive', str(sdk / 'lib/libxos.a'),
                '-Wl,--no-whole-archive', str(sdk / 'cpp/lib/libstdc++.a'),
                str(sdk / 'cpp/lib/libsupc++.a'), str(sdk / 'lib/libc.a'),
                str(sdk / 'lib/libm.a'), str(sdk / 'cpp/lib/libgcc.a'),
                '-Wl,--end-group', '-o', str(elf)]
    commands.extend((compile_cmd, link_cmd))
    with (output / 'compile.log').open('wb') as log:
        subprocess.run(compile_cmd, check=True, env=env, stdout=log, stderr=subprocess.STDOUT)
        subprocess.run(link_cmd, check=True, env=env, stdout=log, stderr=subprocess.STDOUT)

    report = {
        'status': 'FAILED', 'kernel_build_id': system_manifest.get('build_id'),
        'image_sha256': image_digest, 'sdk_manifest_sha256': digest(sdk_manifest),
        'probe_source_sha256': digest(source), 'probe_elf_sha256': digest(elf),
        'commands': commands,
        'scope': ['concurrent call/receive/reply', 'reply/deadline race',
                  'endpoint close wakes blocked receive and call',
                  'per-process endpoint handle quota and repeated recovery',
                  'notification merge/block/wakeup and wait-set event semantics',
                  'wait-set endpoint readiness, close and buffer-too-small retry',
                  'guest resource counters return to baseline'],
        'not_covered': ['global endpoint/call quota saturation across processes',
                        'cross-process exit/exec revocation', 'fault-injected allocation failure'],
        'runs': [],
    }
    guest = None
    try:
        disk = output / 'ipc_v1_work.img'
        create_fat32(disk, 512)
        transfer(disk, 'mkdir', '/bin')
        transfer(disk, 'import', '/bin/ipc_v1_probe.elf', elf)
        guest = Guest(image, 'ipc_v1_guest', work_disk=disk, iso=True)
        report['qemu_command'] = guest.command
        guest.expect(b'xos64> ', timeout=45)
        start = len(guest.output)
        send_bytes(guest, b'run\r')
        guest.expect_supervisor(trace=True, start=start, timeout=45)
        pump(guest, 1.0)
        baseline = resources(guest)
        report['resources_before'] = baseline
        for iteration in range(args.runs):
            result = command(guest, 'exec-file /bin/ipc_v1_probe.elf',
                             b'kind=exited code=', timeout=180)
            if b'[ipc-v1] race-resource' not in result or b' PASS' not in result:
                raise AssertionError(result[-5000:].decode('utf-8', 'replace'))
            if b'kind=exited code=0' not in result:
                raise AssertionError(result[-5000:].decode('utf-8', 'replace'))
            after = resources(guest)
            if after != baseline:
                raise AssertionError(f'guest resource drift: {baseline} -> {after}')
            report['runs'].append({'iteration': iteration, 'resources_after': after})
        command(guest, 'sync', b'sync=ok')
        report['resources_after'] = resources(guest)
        report['status'] = 'PASSED'
    except Exception as error:
        report['error'] = repr(error)
        raise
    finally:
        if guest:
            guest.close()
            for kind in ('serial', 'qemu'):
                log_path = ROOT / f'build/ipc_v1_guest_{kind}.log'
                if log_path.is_file():
                    shutil.copyfile(log_path, output / f'{kind}.log')
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
