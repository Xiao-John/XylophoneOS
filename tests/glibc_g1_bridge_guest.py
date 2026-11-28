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
    parser.add_argument('--system-build', type=Path, default=root / 'build')
    parser.add_argument('--output', type=Path, help='private directory for probe and report')
    parser.add_argument('--yield-build', type=Path, help='G1 diagnostic output containing the real target sched_yield object')
    parser.add_argument('--pid-build', type=Path, help='G1 diagnostic output containing the real target getpid object')
    parser.add_argument('--clock-build', type=Path, help='G1 diagnostic output containing the real target clock_gettime object')
    parser.add_argument('--random-build', type=Path, help='G1 output with target random objects')
    parser.add_argument('--entry-build', type=Path, help='G1 output with target thread entry object')
    parser.add_argument('--exit-build', type=Path, help='G1 output with target thread exit object')
    parser.add_argument('--identity-build', type=Path, help='G1 output with native pthread identity and join objects')
    parser.add_argument('--scheduling-build', type=Path, help='G1 output with native pthread scheduling objects')
    parser.add_argument('--signal-build', type=Path, help='G1 output with native pthread signal and name objects')
    parser.add_argument('--shared-build', type=Path, help='G1 output with named semaphore and shared memory objects')
    parser.add_argument('--memory-build', type=Path, help='G1 output with target heap and VM objects')
    args = parser.parse_args()
    system_build = args.system_build.resolve(strict=True)
    build = args.output.absolute() if args.output else system_build
    if args.output:
        build.mkdir(parents=True, exist_ok=False)
    overlay = root/'src/ports/glibc/sysdeps/xos'
    fixture = root/'tests/fixtures/glibc_g1'
    image = system_build/'xos-install.iso'
    system_manifest = system_build/'manifest.json'
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
    entry_source = overlay.parent/'x86_64/xos/xos_thread_entry.S'
    entry_header = overlay/'xos_thread_entry.h'
    sources.extend([entry_source, entry_header])
    inputs = {str(path.relative_to(root)): sha(path) for path in sources}
    compiler = Path(shutil.which('x86_64-elf-gcc')).resolve(strict=True)
    cmd = [str(compiler), '-std=c11', '-O2', '-mno-red-zone', '-fno-pie', '-fno-pic',
           '-fno-stack-protector', '-ffreestanding', '-nostdlib', '-static', '-no-pie',
           '-Wl,--build-id=none', '-T', str(sources[1]), '-I', str(overlay),
           str(sources[0]), str(sources[2]), '-o', str(probe)]
    entry_provenance = None
    if args.entry_build:
        candidate = args.entry_build.resolve(strict=True)
        entry_report = candidate/'report.json'
        data = json.loads(entry_report.read_text())
        entry_object = candidate/'configure/nptl/xos_thread_entry.o'
        assert data['nptl_backend_experimental'] and not data['hacker_mode']
        assert not data['synthetic_abi_tag'] and data['sysroot_enforced']
        for path in (entry_source, entry_header):
            assert data['xos_overlay_sha256'][str(path.relative_to(overlay.parent))] == sha(path)
        assert data['diagnostic_objects']['xos_thread_entry']['exit_code'] == 0
        assert data['diagnostic_objects']['xos_thread_entry']['sha256'] == sha(entry_object)
        entry_provenance = {'report_sha256': sha(entry_report), 'object_sha256': sha(entry_object)}
        cmd[-2:-2] = [str(entry_object)]
    else:
        cmd[-2:-2] = [str(entry_source)]
    exit_provenance = None
    if args.exit_build:
        candidate = args.exit_build.resolve(strict=True)
        exit_report = candidate/'report.json'
        data = json.loads(exit_report.read_text())
        assert data['nptl_backend_experimental'] and not data['hacker_mode']
        assert not data['synthetic_abi_tag'] and data['sysroot_enforced']
        for name in ('xos_thread_exit.c', 'xos_thread_exit.h'):
            path = overlay/name
            assert data['xos_overlay_sha256']['xos/'+name] == sha(path)
            sources.append(path)
            inputs[str(path.relative_to(root))] = sha(path)
        exit_object = candidate/'configure/nptl/xos_thread_exit.o'
        item = data['diagnostic_objects']['xos_thread_exit']
        assert item['exit_code'] == 0 and item['sha256'] == sha(exit_object)
        exit_provenance = {'report_sha256': sha(exit_report), 'object_sha256': sha(exit_object)}
        cmd[-2:-2] = ['-DXOS_GLIBC_TEST_EXIT', str(exit_object)]
    def bind_thread_objects(candidate, names, headers, define, upstream=(), rt_names=()):
        if candidate is None:
            return None, {}, None
        candidate = candidate.resolve(strict=True)
        report_path = candidate / ('manifest.json' if (candidate / 'manifest.json').is_file() else 'report.json')
        data = json.loads(report_path.read_text())
        complete_sdk = data.get('status') == 'static_sdk_built'
        archive = None
        if complete_sdk:
            archive = candidate / 'sysroot/usr/lib/libc.a'
            assert sha(archive) == data['artifacts']['usr/lib/libc.a']
        else:
            assert data['nptl_backend_experimental'] and not data['hacker_mode']
            assert not data['synthetic_abi_tag'] and data['sysroot_enforced']
        for name in (*[name + '.c' for name in (*names, *rt_names) if name not in upstream],
                     *headers, 'bits/errno.h'):
            path = overlay/name
            digest = sha(path)
            if complete_sdk:
                assert data['inputs'][str(path.relative_to(root))] == digest
            else:
                assert data['xos_overlay_sha256']['xos/'+name] == digest
            if str(path.relative_to(root)) not in inputs:
                sources.append(path)
                inputs[str(path.relative_to(root))] = digest
        objects = {}
        for subdir, name in ([('nptl', name) for name in names]
                             + [('rt', name) for name in rt_names]):
            obj = candidate/'configure'/subdir/(name+'.o')
            if complete_sdk:
                member = subprocess.check_output(['x86_64-elf-ar', 'p', str(archive), name + '.o'])
                assert hashlib.sha256(member).hexdigest() == sha(obj)
            else:
                item = data['diagnostic_objects'][name]
                assert item['exit_code'] == 0 and item['sha256'] == sha(obj)
            objects[obj] = sha(obj)
        provenance = {'report_sha256': sha(report_path),
                      'object_sha256': {obj.name: digest for obj, digest in objects.items()}}
        if complete_sdk:
            provenance['complete_sdk_libc_sha256'] = sha(archive)
        cmd[-2:-2] = [define, *map(str, objects)]
        return report_path, objects, provenance

    identity_report, identity_objects, identity_provenance = bind_thread_objects(
        args.identity_build or args.signal_build,
        ('pthread_self', 'pthread_join_common', 'pthread_detach', 'thrd_current'),
        ('xos_thread_identity.h', 'xos_thread_create.h', 'xos_thread_extensions.h'), '-DXOS_GLIBC_TEST_IDENTITY')
    scheduling_report, scheduling_objects, scheduling_provenance = bind_thread_objects(
        args.scheduling_build,
        ('pthread_getaffinity', 'pthread_setaffinity', 'pthread_getschedparam', 'pthread_setschedparam',
         'pthread_setschedprio', 'pthread_getcpuclockid'),
        ('xos_thread_extensions.h',), '-DXOS_GLIBC_TEST_SCHEDULING')
    signal_report, signal_objects, signal_provenance = bind_thread_objects(
        args.signal_build,
        ('pthread_kill', 'pthread_sigqueue', 'pthread_sigmask', 'xos_thread_name',
         'pthread_getname', 'pthread_setname', 'lowlevellock', 'xos_lll_futex', 'xos_wait_word'),
        ('xos_thread_name.h', 'xos_lll_futex.h', 'xos_wait_word.h'),
        '-DXOS_GLIBC_TEST_SIGNALS', upstream=('lowlevellock',))
    shared_report, shared_objects, shared_provenance = bind_thread_objects(
        args.shared_build, ('sem_open', 'sem_unlink', 'sem_close'),
        ('bits/semaphore.h',), '-DXOS_GLIBC_TEST_SHARED',
        rt_names=('shm_open', 'shm_unlink'))
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
    random_provenance = None
    if args.random_build:
        candidate = args.random_build.resolve(strict=True)
        random_report = candidate/'report.json'
        data = json.loads(random_report.read_text())
        assert data['nptl_backend_experimental'] and not data['hacker_mode']
        assert not data['synthetic_abi_tag'] and data['sysroot_enforced']
        random_objects = []
        for name in ('getrandom', 'getentropy'):
            source = overlay/(name+'.c')
            obj = candidate/'configure/stdlib'/(name+'.o')
            assert data['xos_overlay_sha256']['xos/'+name+'.c'] == sha(source)
            assert data['diagnostic_objects'][name]['exit_code'] == 0
            assert data['diagnostic_objects'][name]['sha256'] == sha(obj)
            inputs[str(source.relative_to(root))] = sha(source)
            sources.append(source)
            random_objects.append(obj)
        random_provenance = {'report_sha256': sha(random_report), 'object_sha256': [sha(x) for x in random_objects]}
        cmd[-2:-2] = ['-DXOS_GLIBC_TEST_RANDOM', *map(str, random_objects)]
    memory_provenance = None
    if args.memory_build:
        candidate = args.memory_build.resolve(strict=True)
        memory_report = candidate/'report.json'
        data = json.loads(memory_report.read_text())
        assert data['nptl_backend_experimental'] and not data['hacker_mode']
        assert not data['synthetic_abi_tag'] and data['sysroot_enforced']
        memory_targets = (
            ('misc', 'brk'), ('elf', 'dl-early_allocate'), ('misc', 'mmap'),
            ('misc', 'mmap64'), ('misc', 'mprotect'), ('misc', 'munmap'),
        )
        for name in ([name + '.c' for _, name in memory_targets]
                     + ['xos_heap_break.h', 'xos_vm.h', 'bits/mman.h', 'bits/errno.h']):
            source = overlay/name
            assert data['xos_overlay_sha256']['xos/'+name] == sha(source)
            inputs[str(source.relative_to(root))] = sha(source)
            sources.append(source)
        memory_objects = {}
        for subdir, name in memory_targets:
            obj = candidate/'configure'/subdir/(name+'.o')
            assert data['diagnostic_objects'][name]['exit_code'] == 0
            assert data['diagnostic_objects'][name]['sha256'] == sha(obj)
            memory_objects[obj] = sha(obj)
        memory_provenance = {'report_sha256': sha(memory_report),
                             'object_sha256': {obj.name: digest for obj, digest in memory_objects.items()}}
        cmd[-2:-2] = ['-DXOS_GLIBC_TEST_MEMORY', *map(str, memory_objects)]
    subprocess.run(cmd, check=True)
    assert inputs == {str(path.relative_to(root)): sha(path) for path in sources}
    report = {'status': 'failed', 'scope': 'freestanding XOS bridge with optional glibc target objects',
              'build_id': system['build_id'], 'system_manifest_sha256': sha(system_manifest),
              'image_sha256': sha(image), 'probe_sha256': sha(probe), 'inputs': inputs,
              'compiler_command': cmd, 'compiler_sha256': sha(compiler), 'yield_provenance': yield_provenance, 'pid_provenance': pid_provenance, 'clock_provenance': clock_provenance, 'random_provenance': random_provenance,
              'entry_provenance': entry_provenance, 'exit_provenance': exit_provenance,
              'identity_provenance': identity_provenance,
              'scheduling_provenance': scheduling_provenance,
              'signal_provenance': signal_provenance,
              'shared_provenance': shared_provenance,
              'memory_provenance': memory_provenance, 'checks': []}
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
                                'native_thread_c_entry_alignment_and_argument',
                                'child_tls_and_exit', 'join_value', 'four_runs_resources_restored']
            if entry_provenance is not None:
                assert sha(entry_report) == entry_provenance['report_sha256']
                assert sha(entry_object) == entry_provenance['object_sha256']
                report['checks'].append('glibc_target_thread_entry_trampoline')
            if exit_provenance is not None:
                assert sha(exit_report) == exit_provenance['report_sha256']
                assert sha(exit_object) == exit_provenance['object_sha256']
                report['checks'].extend(['glibc_target_thread_exit_preserves_result_width',
                                         'glibc_target_last_thread_process_exit'])
            if identity_provenance is not None:
                assert sha(identity_report) == identity_provenance['report_sha256']
                assert {obj: sha(obj) for obj in identity_objects} == identity_objects
                report['checks'].extend(['glibc_target_pthread_self_matches_kernel_tid',
                                         'glibc_target_join_detach_and_stale_tid'])
            if scheduling_provenance is not None:
                assert sha(scheduling_report) == scheduling_provenance['report_sha256']
                assert {obj: sha(obj) for obj in scheduling_objects} == scheduling_objects
                report['checks'].extend(['glibc_target_unsupported_scheduling_preserves_outputs',
                                         'glibc_target_cpu_clock_binds_live_tid'])
            if signal_provenance is not None:
                assert sha(signal_report) == signal_provenance['report_sha256']
                assert {obj: sha(obj) for obj in signal_objects} == signal_objects
                report['checks'].extend(['glibc_target_thread_names_inherit_and_update',
                                         'glibc_target_signal_zero_and_delivery_errors'])
            if shared_provenance is not None:
                assert sha(shared_report) == shared_provenance['report_sha256']
                assert {obj: sha(obj) for obj in shared_objects} == shared_objects
                report['checks'].append('glibc_target_named_shared_objects_report_unavailable')
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
            if random_provenance is not None:
                assert sha(random_report) == random_provenance['report_sha256']
                assert [sha(x) for x in random_objects] == random_provenance['object_sha256']
                report['checks'].append('glibc_target_random_limits_and_errors')
            if memory_provenance is not None:
                assert sha(memory_report) == memory_provenance['report_sha256']
                assert {obj: sha(obj) for obj in memory_objects} == memory_objects
                report['checks'].extend(['glibc_target_heap_growth_shrink_and_errors',
                                         'glibc_target_anonymous_vm_reserve_protect_unmap_and_errors'])
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
