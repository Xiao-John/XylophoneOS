# SPDX-License-Identifier: Apache-2.0
"""Functional E08-4 gate for the XOS-hosted GCC Seed; the caller runs the guest."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import subprocess
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
from toolchain import tool


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def import_manifest_files(disk, source_root, entries, label):
    source_root = Path(source_root).resolve(strict=True)
    if not isinstance(entries, list) or not entries:
        raise ValueError(f'{label} manifest must contain a non-empty file list')
    files = []
    directories = set()
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f'{label} manifest entries must be objects')
        relative = entry.get('path') or entry.get('relative_path')
        guest_path = entry.get('guest_path')
        expected = entry.get('sha256')
        if not relative or not guest_path or not expected or not guest_path.startswith('/'):
            raise ValueError(f'{label} entries require path, guest_path, and sha256')
        if any(ord(char) < 33 or ord(char) > 126 for char in guest_path):
            raise ValueError(f'{label} guest paths must be printable ASCII without spaces')
        original = source_root / relative
        if original.is_symlink():
            raise ValueError(f'{label} source cannot be a symlink: {relative}')
        source = original.resolve(strict=True)
        if source_root not in source.parents or not source.is_file():
            raise ValueError(f'{label} source must be a regular file under its explicit root: {relative}')
        if sha(source) != expected:
            raise AssertionError(f'{label} provenance mismatch: {relative}')
        if guest_path in seen:
            raise ValueError(f'duplicate {label} guest path: {guest_path}')
        seen.add(guest_path)
        parent = Path(guest_path).parent
        while str(parent) not in ('/', '.'):
            directories.add(parent.as_posix())
            parent = parent.parent
        files.append((guest_path, source, expected))
    for directory in sorted(directories, key=lambda item: (item.count('/'), item)):
        transfer(disk, 'mkdir', directory)
    imported = {}
    for guest_path, source, expected in files:
        transfer(disk, 'import', guest_path, source)
        imported[guest_path] = {'sha256': expected, 'bytes': source.stat().st_size}
    return imported


def guest_tool(seed, name):
    item = seed['tools'][name]
    for entry in seed.get('install_files', []):
        relative = entry.get('path') or entry.get('relative_path')
        path = entry.get('guest_path')
        if relative == item['path'] and path:
            if item.get('guest_path') and item['guest_path'] != path:
                continue
            if entry.get('sha256') != item['sha256']:
                raise ValueError(f'tool and install whitelist hashes differ: {name}')
            if any(ord(char) < 33 or ord(char) > 126 for char in path):
                raise ValueError(f'tool guest path must be printable ASCII without spaces: {name}')
            return path
    raise ValueError(f'Seed manifest has no guest path for tools.{name}')


def read_manifest(path, required_tools=('gcc', 'as', 'ld', 'ar', 'ranlib')):
    path = Path(path).resolve(strict=True)
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or not isinstance(data.get('tools'), dict):
        raise ValueError('Seed manifest must contain a tools object')
    if not isinstance(data.get('install_files'), list):
        raise ValueError('Seed manifest must contain an install_files whitelist')
    for required in required_tools:
        item = data['tools'].get(required)
        if not isinstance(item, dict) or not item.get('path') or not item.get('sha256'):
            raise ValueError(f'Seed manifest tools.{required} must bind path and sha256')
    if not data.get('sdk_manifest') or not data.get('sdk_manifest_sha256'):
        raise ValueError('Seed manifest must bind sdk_manifest and sdk_manifest_sha256')
    return path, data


def verify_current_sdk(sdk_manifest, build_root):
    sdk_root = Path(sdk_manifest).parent
    names = ('crt0.o', 'crt0_libc.o', 'crt0_posix.o', 'lib/libxos.a',
             'lib/libxos_loader.a', 'lib/libc.a', 'lib/libm.a', 'user.ld')
    checked = {}
    for name in names:
        snapshot_file = sdk_root / name
        current_file = Path(build_root) / 'sdk' / name
        if not snapshot_file.is_file() or not current_file.is_file():
            raise AssertionError(f'Seed SDK or current build lacks required file: {name}')
        snapshot_hash = sha(snapshot_file)
        if snapshot_hash != sha(current_file):
            raise AssertionError(f'Seed must be relinked against current SDK: {name}')
        checked[name] = snapshot_hash
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed-manifest', type=Path, required=True)
    parser.add_argument('--seed-root', type=Path, required=True,
                        help='explicit host install root used to resolve install_files paths')
    parser.add_argument('--sysroot-manifest', type=Path, required=True)
    parser.add_argument('--sysroot-root', type=Path, required=True,
                        help='explicit host sysroot directory; never inferred from the host')
    parser.add_argument('--guest-sysroot-root', default='/sysroot')
    parser.add_argument('--guest-gcc', default=None)
    parser.add_argument('--report', type=Path, default=ROOT / 'build/gcc_seed_smoke_report.json')
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
    manifest_path, seed = read_manifest(args.seed_manifest)
    seed_root = args.seed_root.resolve(strict=True)
    sysroot_root = args.sysroot_root.resolve(strict=True)
    sysroot_manifest_path = args.sysroot_manifest.resolve(strict=True)
    sysroot_manifest = json.loads(sysroot_manifest_path.read_text())
    if not seed_root.is_dir() or not sysroot_root.is_dir():
        parser.error('--seed-root and --sysroot-root must be directories')
    if not args.guest_sysroot_root.startswith('/'):
        parser.error('--guest-sysroot-root must be an absolute XOS path')
    if any(char.isspace() for char in args.guest_sysroot_root):
        parser.error('--guest-sysroot-root cannot contain spaces')
    if not isinstance(sysroot_manifest, dict) or not isinstance(sysroot_manifest.get('files'), list):
        raise ValueError('sysroot manifest must contain a files whitelist')
    if any(not isinstance(item, dict) or
           not item.get('guest_path', '').startswith(args.guest_sysroot_root.rstrip('/') + '/')
           for item in sysroot_manifest['files']):
        raise ValueError('every target sysroot guest_path must be under --guest-sysroot-root')
    sdk_manifest = (ROOT / seed['sdk_manifest']).resolve(strict=True)
    if sha(sdk_manifest) != seed['sdk_manifest_sha256']:
        raise AssertionError('Seed SDK provenance differs from its manifest')
    for name, item in seed['tools'].items():
        source = seed_root / item['path']
        if not source.is_file() or sha(source) != item['sha256']:
            raise AssertionError(f'Seed tool provenance mismatch: {name}')
    system = json.loads((ROOT / 'build/manifest.json').read_text())
    image_hash = sha(ROOT / 'build/xos.img')
    recorded_image_hash = system.get('artifacts', {}).get('xos.img', {}).get('sha256')
    if recorded_image_hash and recorded_image_hash != image_hash:
        raise AssertionError('build/xos.img does not match build/manifest.json')
    sdk_files = verify_current_sdk(sdk_manifest, ROOT / 'build')
    report = {'status': 'failed', 'gate': 'E08-4', 'build_id': system['build_id'],
              'xos_sha256': image_hash, 'seed_manifest': str(manifest_path),
              'seed_manifest_sha256': sha(manifest_path), 'sdk_manifest_sha256': sha(sdk_manifest),
              'sdk_files_sha256': sdk_files,
              'sysroot_manifest': str(sysroot_manifest_path),
              'sysroot_manifest_sha256': sha(sysroot_manifest_path),
              'sysroot_host_path': str(sysroot_root),
              'guest_sysroot_root': args.guest_sysroot_root, 'checks': [], 'commands': [], 'preflight': preflight.to_dict(),
              'resource_samples': [], 'inputs_sha256': {}, 'outputs': {}}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_gcc_seed_') as folder:
            temporary = Path(folder)
            disk = temporary / 'test.img'
            create_fat32(disk, 2048)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'mkdir', '/src')
            transfer(disk, 'mkdir', '/out')
            transfer(disk, 'mkdir', '/tmp')
            seed_files = import_manifest_files(disk, seed_root, seed['install_files'], 'Seed install')
            sysroot_files = import_manifest_files(disk, sysroot_root, sysroot_manifest['files'], 'target sysroot')
            report['seed_files'] = seed_files
            report['sysroot_files'] = sysroot_files
            report['seed_payload'] = {'files': len(seed_files),
                                      'bytes': sum(item['bytes'] for item in seed_files.values())}
            report['sysroot_payload'] = {'files': len(sysroot_files),
                                         'bytes': sum(item['bytes'] for item in sysroot_files.values())}
            fixtures = ROOT / 'tests/fixtures/gcc'
            fixture_hashes = {}
            for source in sorted(fixtures.iterdir()):
                if source.is_file():
                    transfer(disk, 'import', '/src/' + source.name, source)
                    fixture_hashes[source.name] = sha(source)
            report['inputs_sha256'] = fixture_hashes
            guest = boot(disk, 'gcc_seed_smoke')
            baseline = resources(guest)
            report['baseline_resources'] = baseline
            gcc = args.guest_gcc or guest_tool(seed, 'gcc')
            if any(ord(char) < 33 or ord(char) > 126 for char in gcc):
                raise ValueError('--guest-gcc must be printable ASCII without spaces')
            ar = guest_tool(seed, 'ar')
            ranlib = guest_tool(seed, 'ranlib')
            sysroot_flag = '--sysroot=' + args.guest_sysroot_root

            def run(line, expected=0, contains=None, timeout=180):
                started = time.monotonic()
                supervisor_line = guest_command(line, (gcc,))
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
                    raise AssertionError(f'{line}: {output[-3000:]!r}')
                diagnostic = output.split(b'\n', 1)[1] if b'\n' in output else b''
                if contains is not None and contains not in diagnostic:
                    raise AssertionError(f'{line}: missing {contains!r}: {output[-3000:]!r}')
                report['resource_samples'].append({'line': line, 'resources': current})
                if current != baseline:
                    raise AssertionError(f'resource drift after {line}: {current} != {baseline}')
                if diagnostic_result['host_path_leaks']:
                    raise AssertionError('host paths in actual compiler search/child invocation: ' +
                                         repr(diagnostic_result['host_path_leaks']))
                return output

            run(gcc + ' --version', contains=b'GCC')
            compile_trace = run(gcc + ' -v ' + sysroot_flag + ' -I/src -c /src/value.c -o /out/value.o',
                                contains=b'cc1')
            if re.search(rb'(?:^\s*|/)(?:x86_64-elf-)?as(?:\s|$)', compile_trace, re.MULTILINE) is None:
                raise AssertionError('GCC -v trace did not show the real assembler invocation')
            run(gcc + ' -v ' + sysroot_flag + ' -I/src -c /src/answer.c -o /out/answer.o', contains=b'cc1')
            run(gcc + ' ' + sysroot_flag + ' -I/src -c /src/main.c -o /out/main.o')
            run(ar + ' rcS /out/libanswer.a /out/answer.o /out/value.o')
            run(ranlib + ' /out/libanswer.a')
            link_trace = run(gcc + ' -v -static ' + sysroot_flag + ' -I/src /out/main.o /out/libanswer.a -o /out/app.elf',
                             contains=b'ld')
            if re.search(rb'(?:^\s*|/)(?:x86_64-elf-)?ld(?:\s|$)', link_trace, re.MULTILINE) is None:
                raise AssertionError('GCC -v trace did not show the real linker invocation')
            run('/out/app.elf')
            report['checks'].append('real_driver_cc1_as_ld_multifile_static_archive_link_and_guest_execution')
            run(gcc + ' -v ' + sysroot_flag + ' -I/src -c /src/libgcc.c -o /out/libgcc.o', contains=b'cc1')
            run(gcc + ' -v -static ' + sysroot_flag + ' /out/libgcc.o -o /out/libgcc.elf', contains=b'ld')
            run('/out/libgcc.elf')
            report['checks'].append('guest_object_references_libgcc_128bit_helpers_then_static_link_and_execute')
            run(gcc + ' ' + sysroot_flag + ' -I/src -c /src/syntax_error.c -o /out/syntax.o',
                expected=None, contains=b'error:')
            run(gcc + ' -static ' + sysroot_flag + ' -I/src /src/link_error.c -o /out/link_error.elf',
                expected=None, contains=b'deliberately_missing_symbol')
            run(gcc + ' ' + sysroot_flag + ' -I/src -c /src/header_error.c -o /out/header_error.o',
                expected=None, contains=b'xos_seed_header_that_does_not_exist.h')
            run(gcc + ' ' + sysroot_flag + ' -c /src/no_such_source.c -o /out/missing.o',
                expected=None, contains=b'No such file')
            report['checks'].append('syntax_link_missing_header_and_source_errors_are_nonzero')
            command(guest, 'sync', b'[files] sync=ok')
            guest.close()
            guest = None
            for name, expected in fixture_hashes.items():
                exported = temporary / ('source_' + name)
                transfer(disk, 'export', '/src/' + name, exported)
                if sha(exported) != expected:
                    raise AssertionError(f'guest modified input source: {name}')
            report['checks'].append('all_source_fixtures_preserved_byte_for_byte')
            exported_libgcc_object = temporary / 'guest_libgcc.o'
            transfer(disk, 'export', '/out/libgcc.o', exported_libgcc_object)
            undefined = subprocess.check_output([tool('nm'), '-u', str(exported_libgcc_object)], text=True)
            report['libgcc_object_undefined_symbols'] = undefined
            if '__udivti3' not in undefined or '__umodti3' not in undefined:
                raise AssertionError(f'128-bit arithmetic did not reference libgcc helpers: {undefined}')
            for name in ('value.o', 'answer.o', 'main.o', 'libanswer.a', 'app.elf', 'libgcc.o', 'libgcc.elf'):
                exported = temporary / name
                transfer(disk, 'export', '/out/' + name, exported)
                report['outputs'][name] = {'bytes': exported.stat().st_size, 'sha256': sha(exported)}
            report['status'] = 'passed'
            print(f"PASS: E08-4 GCC Seed functional gate ({len(report['checks'])} groups)")
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
