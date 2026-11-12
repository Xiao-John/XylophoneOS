#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build and run the IPC IP5 latency/semantic probe in an XOS guest.

This records QEMU timing distributions for comparison only; it does not claim
hardware latency, and it must use a system image and threading SDK from the
same source/toolchain build.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

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
    args = parser.parse_args()
    system, sdk = args.system.resolve(), args.sdk.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    image, system_manifest_path = system / 'xos-install.iso', system / 'manifest.json'
    sdk_manifest = sdk / 'manifest.json'
    required = (image, system_manifest_path, sdk_manifest, sdk / 'crt0_posix.o',
                sdk / 'user.ld', sdk / 'lib/libxos.a', sdk / 'lib/libc.a',
                sdk / 'lib/libm.a', sdk / 'cpp/lib/libstdc++.a',
                sdk / 'cpp/lib/libsupc++.a', sdk / 'cpp/lib/libgcc.a')
    for path in required:
        if not path.is_file():
            parser.error(f'missing required input: {path}')
    system_data = json.loads(system_manifest_path.read_text())
    sdk_data = json.loads(sdk_manifest.read_text())
    image_hash = digest(image)
    if system_data.get('artifacts', {}).get('xos-install.iso', {}).get('sha256') != image_hash:
        parser.error('system image hash does not match system manifest')
    for relative, expected in sdk_data.get('artifacts', {}).items():
        artifact = sdk / relative
        if not artifact.is_file() or digest(artifact) != expected:
            parser.error(f'threading SDK artifact differs from manifest: {relative}')

    env = os.environ.copy()
    tools_dir = sdk.parent / 'threading_probe_tools'
    if tools_dir.is_dir():
        env['COMPILER_PATH'] = str(tools_dir)
    source = ROOT / 'tests/fixtures/ipc_v1_fastpath/ipc_v1_fastpath_probe.cpp'
    obj, elf = output / 'ipc_v1_fastpath_probe.o', output / 'ipc_v1_fastpath_probe.elf'
    common = ['-std=c++20', '-O2', '-g', '-fno-pic', '-fno-pie', *X86_FLAGS,
              '-fno-stack-protector', '-fno-exceptions', '-fno-rtti',
              '-ftls-model=local-exec', '-D_POSIX_C_SOURCE=200809L',
              '-DXOS_THREADED_RUNTIME', '-I' + str(ROOT / 'src/user/include'),
              '-I' + str(ROOT / 'src/shared/include'), '-I' + str(sdk / 'cpp/include'),
              '-I' + str(sdk / 'cpp/include/x86_64-elf'), '-I' + str(sdk / 'include')]
    compile_cmd = [tool('g++'), *common, '-c', str(source), '-o', str(obj)]
    link_cmd = [tool('g++'), '-nostdlib', '-static', '-no-pie',
                '-Wl,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
                '-T', str(sdk / 'user.ld'), str(sdk / 'crt0_posix.o'), str(obj),
                '-Wl,--start-group', '-Wl,--whole-archive', str(sdk / 'lib/libxos.a'),
                '-Wl,--no-whole-archive', str(sdk / 'cpp/lib/libstdc++.a'),
                str(sdk / 'cpp/lib/libsupc++.a'), str(sdk / 'lib/libc.a'),
                str(sdk / 'lib/libm.a'), str(sdk / 'cpp/lib/libgcc.a'),
                '-Wl,--end-group', '-o', str(elf)]
    with (output / 'compile.log').open('wb') as log:
        subprocess.run(compile_cmd, check=True, env=env, stdout=log, stderr=subprocess.STDOUT)
        subprocess.run(link_cmd, check=True, env=env, stdout=log, stderr=subprocess.STDOUT)

    report = {
        'status': 'FAILED', 'kernel_build_id': system_data.get('build_id'),
        'image_sha256': image_hash, 'sdk_manifest_sha256': digest(sdk_manifest),
        'probe_source_sha256': digest(source), 'probe_elf_sha256': digest(elf),
        'scope': ['IPC feature query and 0x0f supported mask',
                  'same-process blocked-receiver and polling-fallback distributions',
                  '0/8/64/128/256 byte payloads, 120 samples per case',
                  'reply label/data equality and endpoint/thread cleanup'],
        'limitations': ['QEMU timings are not hardware performance claims',
                        'kernel direct-switch eligibility requires request and reply capacities at most 64 bytes',
                        'polling fallback is a distinct server strategy, not a forced kernel slow-path switch'],
    }
    guest = None
    try:
        disk = output / 'ipc_v1_fastpath_work.img'
        create_fat32(disk, 512)
        transfer(disk, 'mkdir', '/bin')
        transfer(disk, 'import', '/bin/ipc_v1_fastpath_probe.elf', elf)
        guest = Guest(image, 'ipc_v1_fastpath_guest', work_disk=disk, iso=True)
        report['qemu_command'] = guest.command
        guest.expect(b'xos64> ', timeout=45)
        start = len(guest.output)
        send_bytes(guest, b'run\r')
        guest.expect_supervisor(trace=True, start=start, timeout=45)
        pump(guest, 1.0)
        report['resources_before'] = resources(guest)
        result = command(guest, 'exec-file /bin/ipc_v1_fastpath_probe.elf',
                         b'kind=exited code=', timeout=300)
        report['probe_output'] = result.decode('utf-8', 'replace')
        if b'[ipc-ip5] semantics-mask resource-close PASS' not in result or b'kind=exited code=0' not in result:
            raise AssertionError(report['probe_output'][-8000:])
        if result.count(b'[ipc-ip5] mode=') != 10:
            raise AssertionError('expected ten mode/payload distributions')
        report['resources_after'] = resources(guest)
        if report['resources_after'] != report['resources_before']:
            raise AssertionError(f"guest resource drift: {report['resources_before']} -> {report['resources_after']}")
        command(guest, 'sync', b'sync=ok')
        report['status'] = 'PASSED'
    except Exception as error:
        report['error'] = repr(error)
        raise
    finally:
        if guest:
            guest.close()
            for kind in ('serial', 'qemu'):
                log_path = ROOT / f'build/ipc_v1_fastpath_guest_{kind}.log'
                if log_path.is_file():
                    shutil.copyfile(log_path, output / f'{kind}.log')
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
