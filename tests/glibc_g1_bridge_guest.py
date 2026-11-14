#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the freestanding XOS thread bridge in a real, privately booted guest."""
import argparse
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--yield-build', type=Path, help='G1 diagnostic output containing the real target sched_yield object')
    parser.add_argument('--pid-build', type=Path, help='G1 diagnostic output containing the real target getpid object')
    parser.add_argument('--clock-build', type=Path, help='G1 diagnostic output containing the real target clock_gettime object')
    args = parser.parse_args()
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
    yield_provenance = None
    if args.yield_build:
        candidate = args.yield_build.resolve(strict=True)
        source_report = candidate/'report.json'
        source_data = json.loads(source_report.read_text())
        yield_object = candidate/'configure/posix/sched_yield.o'
        yield_source = overlay/'sched_yield.c'
        assert source_data['nptl_backend_experimental'] and not source_data['hacker_mode']
        assert not source_data['synthetic_abi_tag'] and source_data['sysroot_enforced']
        assert source_data['xos_overlay_sha256']['xos/sched_yield.c'] == sha(yield_source)
        assert source_data['diagnostic_objects']['sched_yield']['exit_code'] == 0
        assert source_data['diagnostic_objects']['sched_yield']['sha256'] == sha(yield_object)
        inputs[str(yield_source.relative_to(root))] = sha(yield_source)
        sources.append(yield_source)
        yield_provenance = {'report_sha256': sha(source_report), 'object_sha256': sha(yield_object)}
        cmd[-2:-2] = ['-DXOS_GLIBC_TEST_YIELD', str(yield_object)]
    pid_provenance = None
    if args.pid_build:
        pid_candidate = args.pid_build.resolve(strict=True)
        pid_report = pid_candidate/'report.json'
        pid_data = json.loads(pid_report.read_text())
        pid_object = pid_candidate/'configure/posix/getpid.o'
        pid_source = overlay/'getpid.c'
        assert pid_data['nptl_backend_experimental'] and not pid_data['hacker_mode']
        assert not pid_data['synthetic_abi_tag'] and pid_data['sysroot_enforced']
        assert pid_data['xos_overlay_sha256']['xos/getpid.c'] == sha(pid_source)
        assert pid_data['diagnostic_objects']['getpid']['exit_code'] == 0
        assert pid_data['diagnostic_objects']['getpid']['sha256'] == sha(pid_object)
        inputs[str(pid_source.relative_to(root))] = sha(pid_source)
        sources.append(pid_source)
        pid_provenance = {'report_sha256': sha(pid_report), 'object_sha256': sha(pid_object)}
        cmd[-2:-2] = ['-DXOS_GLIBC_TEST_GETPID', str(pid_object)]
    clock_provenance = None
    if args.clock_build:
        clock_candidate = args.clock_build.resolve(strict=True)
        clock_report = clock_candidate/'report.json'
        clock_data = json.loads(clock_report.read_text())
        clock_object = clock_candidate/'configure/time/clock_gettime.o'
        clock_source = overlay/'clock_gettime.c'
        res_source = overlay/'clock_getres.c'
        res_object = clock_candidate/'configure/time/clock_getres.o'
        clock_helper = overlay/'xos_clock.h'
        clock_header = overlay/'xos_cpu_time.h'
        assert clock_data['nptl_backend_experimental'] and not clock_data['hacker_mode']
        assert not clock_data['synthetic_abi_tag'] and clock_data['sysroot_enforced']
        assert clock_data['xos_overlay_sha256']['xos/clock_gettime.c'] == sha(clock_source)
        assert clock_data['diagnostic_objects']['clock_gettime']['exit_code'] == 0
        assert clock_data['diagnostic_objects']['clock_gettime']['sha256'] == sha(clock_object)
        assert clock_data['diagnostic_objects']['clock_getres']['exit_code'] == 0
        assert clock_data['diagnostic_objects']['clock_getres']['sha256'] == sha(res_object)
        assert clock_data['xos_overlay_sha256']['xos/clock_getres.c'] == sha(res_source)
        assert clock_data['xos_overlay_sha256']['xos/xos_clock.h'] == sha(clock_helper)
        assert clock_data['xos_overlay_sha256']['xos/xos_cpu_time.h'] == sha(clock_header)
        inputs[str(clock_source.relative_to(root))] = sha(clock_source)
        inputs[str(clock_header.relative_to(root))] = sha(clock_header)
        inputs[str(res_source.relative_to(root))] = sha(res_source)
        inputs[str(clock_helper.relative_to(root))] = sha(clock_helper)
        sources.extend([clock_source, clock_header, res_source, clock_helper])
        clock_provenance = {'report_sha256': sha(clock_report), 'object_sha256': sha(clock_object), 'resolution_sha256': sha(res_object)}
        cmd[-2:-2] = ['-DXOS_GLIBC_TEST_CLOCK', str(clock_object), str(res_object)]
    subprocess.run(cmd, check=True)
    assert inputs == {str(path.relative_to(root)): sha(path) for path in sources}
    report = {'status': 'failed', 'scope': 'freestanding XOS thread bridge; no glibc linked',
              'build_id': system['build_id'], 'system_manifest_sha256': sha(system_manifest),
              'image_sha256': sha(image), 'probe_sha256': sha(probe), 'inputs': inputs,
              'compiler_command': cmd, 'compiler_sha256': sha(compiler), 'yield_provenance': yield_provenance, 'pid_provenance': pid_provenance, 'clock_provenance': clock_provenance, 'checks': []}
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
            if yield_provenance is not None:
                assert sha(source_report) == yield_provenance['report_sha256']
                assert sha(yield_object) == yield_provenance['object_sha256']
                report['checks'].append('glibc_target_sched_yield_between_threads')
            if pid_provenance is not None:
                assert sha(pid_report) == pid_provenance['report_sha256']
                assert sha(pid_object) == pid_provenance['object_sha256']
                report['checks'].append('glibc_target_getpid_same_process_across_threads')
            if clock_provenance is not None:
                assert sha(clock_report) == clock_provenance['report_sha256']
                assert sha(clock_object) == clock_provenance['object_sha256']
                assert sha(res_object) == clock_provenance['resolution_sha256']
                report['checks'].append('glibc_target_clock_matches_native_and_rejects_unknown')
                for output in outputs:
                    assert '[g1] cpu_time=available' in output or '[g1] cpu_time=unavailable' in output
                report['cpu_time_modes'] = ['available' if '[g1] cpu_time=available' in output else 'unavailable' for output in outputs]
                report['checks'].append('glibc_target_cpu_clock_matches_native_or_reports_unavailable')
                report['checks'].append('glibc_target_clock_resolution_matches_native')
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
