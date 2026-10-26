# SPDX-License-Identifier: Apache-2.0
"""Real guest pthread/newlib pipe blocking, close leases, and numeric FD reuse."""
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
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from toolchain import tool
from work_disk import transfer


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, default=ROOT/'build')
    parser.add_argument('--sdk', type=Path, default=ROOT/'build/threading_sdk')
    parser.add_argument('--report', type=Path, default=ROOT/'build/dash_c1_pthread_report.json')
    parser.add_argument('--artifacts', type=Path, default=ROOT/'build/dash_c1_pthread_evidence')
    parser.add_argument('--repeat', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeat <= 5: parser.error('--repeat must be between 1 and 5')
    args.system, args.sdk, args.artifacts = args.system.resolve(), args.sdk.resolve(), args.artifacts.resolve()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    report = {'status': 'failed', 'scope': 'pthread/newlib blocking pipe I/O and in-flight FD leases',
              'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'sources': {}, 'tools': {}, 'build_commands': [], 'runs': [], 'checks': [],
              'not_run': ['SMP', 'long_randomized_stress']}
    guest = None
    try:
        system_path = args.system/'manifest.json'
        sdk_path = args.sdk/'manifest.json'
        system, sdk = json.loads(system_path.read_text()), json.loads(sdk_path.read_text())
        report.update(system_build_id=system['build_id'], system_manifest_sha256=sha(system_path),
                      sdk_manifest_sha256=sha(sdk_path), sdk_profile=sdk['profile'],
                      sdk_recorded_qualification=sdk.get('qualification'))
        image = args.system/'xos.img'
        report['image_sha256'] = sha(image)
        if sha(image) != system['artifacts']['xos.img']['sha256']:
            raise AssertionError('system image differs from manifest')
        # Validate every frozen SDK artifact and every local source receipt,
        # including the branch's actual newlib syscall implementation.
        for relative, expected in sdk['artifacts'].items():
            if sha(args.sdk/relative) != expected:
                raise AssertionError('SDK artifact differs from receipt: '+relative)
        for relative, expected in sdk['inputs'].items():
            if sha(ROOT/relative) != expected:
                raise AssertionError('SDK input source differs from receipt: '+relative)
        report['sdk_artifacts'] = sdk['artifacts']
        report['sdk_inputs'] = sdk['inputs']
        source = ROOT/'tests/fixtures/dash_c1/pipe_pthread.cpp'
        for path in (source, Path(__file__).resolve(), ROOT/'src/kernel/arch/x86_64/tasks.cpp',
                     ROOT/'src/user/libc/newlib_syscalls.cpp'):
            report['sources'][str(path.relative_to(ROOT))] = sha(path)
        compiler = tool('g++')
        target_tools = ROOT/'build/target_tools'
        for name, path in (('g++', Path(compiler)), ('as', target_tools/'as'), ('ld', target_tools/'ld')):
            report['tools'][name] = {'path': str(path.resolve()), 'sha256': sha(path),
                'version': subprocess.check_output([str(path), '--version'], text=True).splitlines()[0]}
        obj, executable = args.artifacts/'pipe_pthread.o', args.artifacts/'pipe_pthread.elf'

        def build(line, logfile):
            report['build_commands'].append([str(value) for value in line])
            result = subprocess.run(line, capture_output=True, text=True)
            (args.artifacts/logfile).write_text(result.stdout+result.stderr)
            if result.returncode: raise AssertionError(f'probe build failed {result.returncode}: {logfile}')

        build([compiler, '-B'+str(target_tools)+'/', '-std=c++20', '-O2', '-g', '-fno-pic', '-fno-pie',
               '-mno-red-zone', '-fno-stack-protector', '-ftls-model=local-exec',
               '-D_POSIX_C_SOURCE=200809L', '-DXOS_THREADED_RUNTIME',
               '-I'+str(args.sdk/'cpp/include'), '-I'+str(args.sdk/'cpp/include/x86_64-elf'),
               '-I'+str(args.sdk/'include'), '-c', str(source), '-o', str(obj)], 'compile.log')
        build([compiler, '-B'+str(target_tools)+'/', '-nostdlib', '-static', '-no-pie',
               '-Wl,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
               '-T', str(args.sdk/'user.ld'), str(args.sdk/'crt0_posix.o'), str(obj),
               '-Wl,--start-group', '-Wl,--whole-archive', str(args.sdk/'lib/libxos.a'), '-Wl,--no-whole-archive',
               str(args.sdk/'cpp/lib/libstdc++.a'), str(args.sdk/'cpp/lib/libsupc++.a'),
               str(args.sdk/'lib/libc.a'), str(args.sdk/'lib/libm.a'), str(args.sdk/'cpp/lib/libgcc.a'),
               '-Wl,--end-group', '-o', str(executable)], 'link.log')
        report['probe'] = {'path': str(executable), 'bytes': executable.stat().st_size,
                           'sha256': sha(executable), 'object_sha256': sha(obj)}
        with tempfile.TemporaryDirectory(prefix='xos_c1_pthread_') as folder_name:
            folder = Path(folder_name)
            private_image, disk = folder/'boot.img', folder/'work.img'
            shutil.copyfile(image, private_image)
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/tests')
            transfer(disk, 'import', '/tests/pipe_pthread', executable)
            guest = Guest(private_image, 'dash_c1_pthread', work_disk=disk)
            report['qemu_command'] = guest.command
            qemu = Path(guest.command[0])
            report['tools']['qemu'] = {'path': str(qemu.resolve()), 'sha256': sha(qemu),
                'version': subprocess.check_output([str(qemu), '--version'], text=True).splitlines()[0]}
            guest.expect(b'xos64> ', timeout=40)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=40)
            pump(guest, 1.5)
            baseline = resources(guest)
            report['baseline_resources'] = baseline
            markers = (
                b'C1_PTHREAD blocked_read_write_wake=ok',
                b'C1_PTHREAD blocked_full_write_read_wake=ok',
                b'C1_PTHREAD close_keeps_inflight_lease numeric_fd_reuse_isolated=ok',
                b'C1_PTHREAD close_last_writer_wakes_blocked_libc_read_eof=ok',
                b'C1_PTHREAD resources=baseline PASS',
            )
            for iteration in range(args.repeat):
                record = {'iteration': iteration, 'command': 'exec-file /tests/pipe_pthread',
                          'expected_exit': 0, 'expected_resources': baseline,
                          'expected_output': [marker.decode() for marker in markers], 'status': 'failed'}
                report['runs'].append(record)
                start = len(guest.output)
                try:
                    output = command(guest, record['command'], b'kind=exited code=', timeout=90)
                    record['output'] = output.decode(errors='replace')
                    if b'C1_PTHREAD_FAIL' in output or b'C1_PTHREAD_TIMEOUT' in output:
                        raise AssertionError(f'guest failure/watchdog in iteration {iteration}')
                    if b'kind=exited code=0' not in output:
                        raise AssertionError(f'guest did not exit zero in iteration {iteration}')
                    for marker in markers:
                        if marker not in output: raise AssertionError(f'missing marker {marker!r}')
                    counters = []
                    for label, fields in re.findall(rb'C1_PTHREAD_COUNTERS (\S+) ([^\r\n]+)', output):
                        values = {key.decode(): int(value) for key, value in re.findall(rb'(\w+)=(\d+)', fields)}
                        counters.append({'phase': label.decode(), **values})
                    record['guest_resource_counters'] = counters
                    if [item['phase'] for item in counters] != [
                        'initial', 'steady_with_watchdog', 'read_wake_end', 'full_wake_end',
                        'close_reuse_end', 'eof_end', 'final']:
                        raise AssertionError('missing guest per-case resource counters')
                    after = resources(guest)
                    record['actual_resources'] = after
                    if after != baseline:
                        raise AssertionError(f'guest resources {after} differ from {baseline}')
                    record.update(status='passed', actual_exit=0)
                finally:
                    logfile = args.artifacts/f'iteration_{iteration}.serial.log'
                    logfile.write_bytes(bytes(guest.output[start:]))
                    record['serial_log'] = {'path': str(logfile), 'sha256': sha(logfile)}
            report['final_resources'] = resources(guest)
            report['checks'] = [marker.decode() for marker in markers]
            report['status'] = 'passed'
    except Exception as error:
        report['error'] = str(error)
        if guest is not None: report['output_tail'] = bytes(guest.output[-16000:]).decode(errors='replace')
        raise
    finally:
        if guest is not None:
            logfile = args.artifacts/'all.serial.log'
            logfile.write_bytes(bytes(guest.output))
            report['serial_log'] = {'path': str(logfile), 'sha256': sha(logfile)}
            guest.close()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
