# SPDX-License-Identifier: Apache-2.0
"""Functional E08-5 gate for the XOS-hosted G++ Seed; the caller runs the guest."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from make_work_disk import create_fat32
from work_disk import transfer
from e08_storage_smoke import boot
from process_smoke import command, resources
from seed_diagnostics import diagnose, guest_command
from seed_preflight import validate_bundle
from task_smoke import send_bytes
from gcc_seed_smoke import guest_tool, import_manifest_files, read_manifest, sha, verify_current_sdk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed-manifest', type=Path, required=True)
    parser.add_argument('--seed-root', type=Path, required=True)
    parser.add_argument('--sysroot-manifest', type=Path, required=True)
    parser.add_argument('--sysroot-root', type=Path, required=True)
    parser.add_argument('--guest-sysroot-root', default='/sysroot')
    parser.add_argument('--guest-gxx', default=None)
    parser.add_argument('--report', type=Path, default=ROOT / 'build/cpp_seed_smoke_report.json')
    parser.add_argument('--preflight-only', action='store_true', help='validate inputs without creating a disk or launching QEMU')
    args = parser.parse_args()
    required = ('gcc', 'cc1', 'as', 'ld', 'ar', 'ranlib') if 'gcc_seed' in __file__ else ('g++', 'cc1plus', 'as', 'ld', 'ar', 'ranlib')
    preflight = validate_bundle(args.seed_manifest, args.seed_root, args.sysroot_manifest,
                               args.sysroot_root, args.guest_sysroot_root, required)
    if not preflight.ok or args.preflight_only:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({'status': 'preflight_only' if preflight.ok else 'failed_preflight',
                                          'guest_execution': 'not_run', 'preflight': preflight.to_dict()}, indent=2) + '\n')
        print('Preflight:', 'valid' if preflight.ok else 'failed', preflight.summary)
        if not preflight.ok:
            for diagnostic in preflight.diagnostics:
                print(diagnostic['code'], diagnostic['path'], diagnostic['message'])
        return 0 if preflight.ok else 1
    manifest_path, seed = read_manifest(args.seed_manifest, ('g++', 'cc1plus', 'as', 'ld', 'ar', 'ranlib'))
    seed_root = args.seed_root.resolve(strict=True)
    sysroot_root = args.sysroot_root.resolve(strict=True)
    sysroot_manifest_path = args.sysroot_manifest.resolve(strict=True)
    sysroot_manifest = json.loads(sysroot_manifest_path.read_text())
    if not seed_root.is_dir() or not sysroot_root.is_dir():
        parser.error('--seed-root and --sysroot-root must be directories')
    if not args.guest_sysroot_root.startswith('/'):
        parser.error('--guest-sysroot-root must be an absolute XOS path')
    if not isinstance(seed.get('install_files'), list):
        raise ValueError('Seed manifest must contain an install_files whitelist')
    if not isinstance(sysroot_manifest, dict) or not isinstance(sysroot_manifest.get('files'), list):
        raise ValueError('sysroot manifest must contain a files whitelist')
    if any(not isinstance(item, dict) or
           not item.get('guest_path', '').startswith(args.guest_sysroot_root.rstrip('/') + '/')
           for item in sysroot_manifest['files']):
        raise ValueError('every target sysroot guest_path must be under --guest-sysroot-root')
    for required in ('g++', 'cc1plus', 'as', 'ld', 'ar', 'ranlib'):
        item = seed['tools'].get(required)
        if not isinstance(item, dict) or not item.get('path') or not item.get('sha256'):
            raise ValueError(f'Seed manifest tools.{required} must bind path and sha256')
        source = seed_root / item['path']
        if not source.is_file() or sha(source) != item['sha256']:
            raise AssertionError(f'Seed tool provenance mismatch: {required}')
    sdk_manifest = (ROOT / seed['sdk_manifest']).resolve(strict=True)
    if sha(sdk_manifest) != seed['sdk_manifest_sha256']:
        raise AssertionError('Seed SDK provenance differs from its manifest')
    system = json.loads((ROOT / 'build/manifest.json').read_text())
    image_hash = sha(ROOT / 'build/xos.img')
    recorded_image_hash = system.get('artifacts', {}).get('xos.img', {}).get('sha256')
    if recorded_image_hash and recorded_image_hash != image_hash:
        raise AssertionError('build/xos.img does not match build/manifest.json')
    sdk_files = verify_current_sdk(sdk_manifest, ROOT / 'build')
    report = {'status': 'failed', 'gate': 'E08-5', 'seed_manifest': str(manifest_path),
              'build_id': system['build_id'], 'xos_sha256': image_hash,
              'seed_manifest_sha256': sha(manifest_path), 'sdk_manifest_sha256': sha(sdk_manifest),
              'sdk_files_sha256': sdk_files,
              'sysroot_manifest': str(sysroot_manifest_path),
              'sysroot_manifest_sha256': sha(sysroot_manifest_path),
              'sysroot_host_path': str(sysroot_root),
              'guest_sysroot_root': args.guest_sysroot_root, 'checks': [], 'commands': [], 'preflight': preflight.to_dict(),
              'resource_samples': [], 'inputs_sha256': {}, 'outputs': {}}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_cpp_seed_') as folder:
            temporary = Path(folder)
            disk = temporary / 'test.img'
            create_fat32(disk, 2048)
            for path in ('/bin', '/src', '/out', '/tmp'):
                transfer(disk, 'mkdir', path)
            report['seed_files'] = import_manifest_files(disk, seed_root, seed['install_files'], 'Seed install')
            report['sysroot_files'] = import_manifest_files(disk, sysroot_root, sysroot_manifest['files'], 'target sysroot')
            fixtures = ROOT / 'tests/fixtures/cpp'
            fixture_hashes = {}
            for source in sorted(fixtures.iterdir()):
                if source.is_file():
                    transfer(disk, 'import', '/src/' + source.name, source)
                    fixture_hashes[source.name] = sha(source)
            report['inputs_sha256'] = fixture_hashes
            guest = boot(disk, 'cpp_seed_smoke')
            baseline = resources(guest)
            report['baseline_resources'] = baseline
            gxx = args.guest_gxx or guest_tool(seed, 'g++')
            if any(ord(char) < 33 or ord(char) > 126 for char in gxx):
                raise ValueError('--guest-gxx must be printable ASCII without spaces')
            ar = guest_tool(seed, 'ar')
            ranlib = guest_tool(seed, 'ranlib')
            sysroot_flag = '--sysroot=' + args.guest_sysroot_root

            def run(line, expected=0, contains=None, timeout=240):
                started = time.monotonic()
                supervisor_line = guest_command(line, (gxx,))
                output = command(guest, supervisor_line, b'sup> ', timeout=timeout)
                diagnostic_result = diagnose(output, supervisor_line)
                match = re.search(rb'kind=exited code=(-?\d+)', output)
                current = resources(guest)
                report['commands'].append({'line': line, 'supervisor_command': supervisor_line,
                                           'diagnostic': diagnostic_result,
                                           'exit_code': int(match[1]) if match else None,
                                           'elapsed_seconds': time.monotonic() - started,
                                           'resources': current,
                                           'output': output.decode(errors='replace')})
                if match is None or (int(match[1]) != expected if expected is not None else int(match[1]) == 0):
                    raise AssertionError(f'{line}: {output[-3500:]!r}')
                diagnostic = output.split(b'\n', 1)[1] if b'\n' in output else b''
                if contains is not None and contains not in diagnostic:
                    raise AssertionError(f'{line}: missing {contains!r}: {output[-3500:]!r}')
                report['resource_samples'].append({'line': line, 'resources': current})
                if current != baseline:
                    raise AssertionError(f'resource drift after {line}: {current} != {baseline}')
                if diagnostic_result['host_path_leaks']:
                    raise AssertionError('host paths in actual compiler search/child invocation: ' +
                                         repr(diagnostic_result['host_path_leaks']))
                return output

            run(gxx + ' --version', contains=b'GCC')
            for source, output in (('translation_unit.cpp', 'translation_unit.o'),
                                   ('exception_rtti.cpp', 'exception_rtti.o'),
                                   ('tls.cpp', 'tls.o'), ('library.cpp', 'library.o'),
                                   ('main.cpp', 'main.o')):
                run(gxx + ' -v -std=gnu++17 -static ' + sysroot_flag + ' -I/src -c /src/' + source + ' -o /out/' + output,
                    contains=b'cc1plus')
            run(ar + ' rcS /out/libcpp.a /out/library.o')
            run(ranlib + ' /out/libcpp.a')
            link_trace = run(gxx + ' -v -std=gnu++17 -static ' + sysroot_flag + ' /out/main.o /out/translation_unit.o /out/exception_rtti.o /out/tls.o /out/libcpp.a -o /out/cpp_app.elf',
                             contains=b'ld')
            if re.search(rb'(?:^\s*|/)(?:x86_64-elf-)?ld(?:\s|$)', link_trace, re.MULTILINE) is None:
                raise AssertionError('G++ -v trace did not show the real linker invocation')
            run('/out/cpp_app.elf')
            marker = command(guest, 'cat /out/cpp_global_destructor.marker', b'destructed', timeout=20)
            if b'destructed' not in marker:
                raise AssertionError('cross-translation-unit global destructor did not write its marker')
            if resources(guest) != baseline:
                raise AssertionError('C++ runtime probe leaked pages, tasks, or completions')
            report['checks'].append('container_string_local_static_cross_tu_init_tls_before_global_dtor_archive_exception_frames_and_rtti')

            run(gxx + ' -std=gnu++17 -static ' + sysroot_flag + ' -I/src -c /src/tls_worker.cpp -o /out/tls_worker.o')
            run(gxx + ' -static ' + sysroot_flag + ' /out/tls_worker.o /out/tls.o -o /out/cpp_tls_worker.elf')
            before_spawn = resources(guest)
            pids = []
            for value in (4, 7):
                start = len(guest.output)
                send_bytes(guest, f'spawn-file /out/cpp_tls_worker.elf {value}\r'.encode())
                guest.expect(b'[loader] started pid=', start=start, timeout=30)
                guest.expect(b'sup> ', start=start, timeout=30)
                output = bytes(guest.output[start:])
                match = re.search(rb'\[loader\] started pid=(\d+)', output)
                if match is None:
                    raise AssertionError(f'failed to start TLS worker: {output[-1500:]!r}')
                pids.append(int(match[1]))
            if len(set(pids)) != 2:
                raise AssertionError(f'TLS workers did not get distinct tasks: {pids}')
            for pid in pids:
                result = command(guest, f'wait {pid}', b'[wait] pid=', timeout=45)
                if b'kind=exited code=0' not in result:
                    raise AssertionError(f'TLS worker failed: {result[-1500:]!r}')
                current = resources(guest)
                report['resource_samples'].append({'line': f'wait {pid}', 'resources': current})
            if resources(guest) != before_spawn:
                raise AssertionError('TLS workers leaked pages, tasks, or completions')
            report['tls_worker_pids'] = pids
            list_start = len(guest.output)
            send_bytes(guest, b'ls /tmp\r')
            guest.expect(b'sup> ', start=list_start, timeout=20)
            tmp_listing = bytes(guest.output[list_start:])
            report['tls_tmp_listing'] = tmp_listing.decode(errors='replace')
            if b'tls_worker_4.ready' in tmp_listing or b'tls_worker_7.ready' in tmp_listing:
                raise AssertionError('TLS worker left its readiness file behind')
            if resources(guest) != baseline:
                raise AssertionError('TLS worker file check leaked resources')
            report['checks'].append('two_live_tasks_keep_initialized_tls_isolated_across_scheduler_yields_and_reclaim')

            run(gxx + ' -std=gnu++17 ' + sysroot_flag + ' -I/src -c /src/syntax_error.cpp -o /out/syntax.o',
                expected=None, contains=b'error:')
            run(gxx + ' -static ' + sysroot_flag + ' /src/link_error.cpp -o /out/link_error.elf',
                expected=None, contains=b'deliberately_missing_cpp_symbol')
            report['checks'].append('cpp_syntax_and_link_errors_are_nonzero')
            command(guest, 'sync', b'[files] sync=ok')
            guest.close()
            guest = None
            for name, expected in fixture_hashes.items():
                exported = temporary / ('source_' + name)
                transfer(disk, 'export', '/src/' + name, exported)
                if sha(exported) != expected:
                    raise AssertionError(f'guest modified input source: {name}')
            report['checks'].append('all_cpp_source_fixtures_preserved_byte_for_byte')
            for name in ('translation_unit.o', 'exception_rtti.o', 'tls.o', 'library.o',
                         'main.o', 'libcpp.a', 'cpp_app.elf', 'cpp_tls_worker.elf'):
                exported = temporary / name
                transfer(disk, 'export', '/out/' + name, exported)
                report['outputs'][name] = {'bytes': exported.stat().st_size, 'sha256': sha(exported)}
            report['status'] = 'passed'
            print(f"PASS: E08-5 C++ Seed functional gate ({len(report['checks'])} groups)")
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if guest is not None:
            guest.close()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
