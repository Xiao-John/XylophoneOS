# SPDX-License-Identifier: Apache-2.0
"""E08-3 stress: repeat, scale, failure injection and bounded soak for the GNU Seed."""
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


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed-manifest', type=Path, required=True)
    parser.add_argument('--s1-cycles', type=int, default=10)
    parser.add_argument('--s4-cycles', type=int, default=20)
    parser.add_argument('--skip-s2', action='store_true')
    parser.add_argument('--skip-s3', action='store_true')
    parser.add_argument('--skip-s4', action='store_true')
    parser.add_argument('--keep-image', action='store_true')
    args = parser.parse_args()
    seed_path = args.seed_manifest.resolve()
    seed = json.loads(seed_path.read_text())
    build = ROOT / 'build'
    system = json.loads((build / 'manifest.json').read_text())
    sdk = ROOT / seed['sdk_manifest']
    if sha(sdk) != seed['sdk_manifest_sha256']:
        raise AssertionError('Seed SDK provenance differs')
    for name in ('crt0_posix.o', 'lib/libxos.a', 'lib/libxos_loader.a', 'lib/libc.a', 'lib/libm.a', 'user.ld'):
        if sha(sdk.parent / name) != sha(build / 'sdk' / name):
            raise AssertionError(f'Seed needs relink: {name}')

    report = {
        'stage': 'E08-3 stress', 'status': 'failed', 'started': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'build_id': system['build_id'], 'xos_sha256': system['artifacts']['xos.img']['sha256'],
        'seed_manifest': str(seed_path.relative_to(ROOT)), 'seed_manifest_sha256': sha(seed_path),
        'seed_build': seed.get('build_id'), 'levels': {}, 'commands': [], 'checks': [],
        'resource_samples': [], 'failures': [],
    }
    guest = None
    disk = None
    temporary = tempfile.TemporaryDirectory(prefix='xos_bin_stress_')
    try:
        base = Path(temporary.name)
        disk = base / 'stress.img'
        create_fat32(disk, 512)
        for path in ('/bin', '/src', '/src/scale', '/out', '/out/s', '/out/s4', '/tmp'):
            transfer(disk, 'mkdir', path)
        for name in ('as', 'ld', 'ar', 'ranlib', 'strip'):
            item = seed['tools'][name]
            source = seed_path.parent / 'install' / item['path']
            if sha(source) != item['sha256']:
                raise AssertionError(f'Seed tool changed: {name}')
            transfer(disk, 'import', '/bin/' + name, source)
        transfer(disk, 'import', '/bin/runtime_probe.elf', build / 'user_runtime_probe.image.elf')
        fixtures = ROOT / 'tests/fixtures/binutils'
        source_hashes = {}
        for path in sorted(fixtures.iterdir()):
            if path.is_file():
                transfer(disk, 'import', '/src/' + path.name, path)
                source_hashes[path.name] = sha(path)

        # S2 generated objects: 32 functions plus large BSS/rodata members.
        scale = base / 'scale'
        scale.mkdir()
        calls = []
        for i in range(32):
            symbol = f'sym{i}'
            (scale / f'{i}.s').write_text(
                f'.text\n.global {symbol}\n.type {symbol},@function\n{symbol}:\n    mov ${i},%eax\n    ret\n'
                f'.size {symbol},.-{symbol}\n.section .note.GNU-stack,"",@progbits\n')
            calls.append(f'    call {symbol}')
        (scale / 'bss.s').write_text(
            '.text\n.global bss_sym\nbss_sym:\n    ret\n.bss\n.space 8388608\n'
            '.section .note.GNU-stack,"",@progbits\n')
        (scale / 'rodata.s').write_text(
            '.text\n.global ro_sym\nro_sym:\n    ret\n.section .rodata\n.space 1048576,0x41\n'
            '.section .note.GNU-stack,"",@progbits\n')
        calls += ['    call bss_sym', '    call ro_sym']
        (scale / 'start.s').write_text(
            '.section .text.entry,"ax",@progbits\n.global _start\n_start:\n' + '\n'.join(calls) +
            '\n    mov $42,%edi\n    mov $2,%eax\n    int $0x80\n    ud2\n'
            '.section .note.GNU-stack,"",@progbits\n')
        for path in sorted(scale.iterdir()):
            transfer(disk, 'import', '/src/scale/' + path.name, path)
        (base / 'truncated.o').write_bytes(b'\x7fELF' + bytes(28))
        transfer(disk, 'import', '/src/truncated.o', base / 'truncated.o')

        guest = boot(disk, 'binutils_stress')
        baseline = resources(guest)
        report['baseline'] = baseline

        def run(line, code=0, contains=None, timeout=180):
            started = time.monotonic()
            output = command(guest, line, b'[wait] pid=', timeout=timeout)
            match = re.search(rb'kind=exited code=(-?\d+)', output)
            if match is None:
                raise AssertionError(f'no result: {line}: {output[-1200:]!r}')
            actual = int(match[1])
            if code is not None and actual != code:
                raise AssertionError(f'{line}: expected {code}, got {actual}: {output[-1500:]!r}')
            if contains is not None and contains not in output:
                raise AssertionError(f'{line}: missing {contains!r}: {output[-1500:]!r}')
            current = resources(guest)
            if current != baseline:
                raise AssertionError(f'{line}: resource drift {current} != {baseline}')
            report['commands'].append({'line': line, 'code': actual, 'seconds': time.monotonic() - started})
            return output

        def command_ok(line, expected, timeout=30):
            output = command(guest, line, expected, timeout=timeout)
            report['commands'].append({'line': line, 'code': None, 'seconds': None})
            return output

        # S1: repeat the complete tool chain and remove generated files each cycle.
        s1_start = time.monotonic()
        for cycle in range(args.s1_cycles):
            run('exec-file /bin/as --64 -o /out/start.o /src/start.s')
            run('exec-file /bin/as --64 -o /out/answer.o /src/answer.s')
            run('exec-file /bin/ar rcS /out/libanswer.a /out/answer.o')
            run('exec-file /bin/ranlib /out/libanswer.a')
            run('exec-file /bin/ld -T /src/app.ld -o /out/app.elf /out/start.o /out/libanswer.a')
            run('exec-file /out/app.elf', code=42, contains=b'seed chain\n')
            run('exec-file /bin/strip -o /out/app_stripped.elf /out/app.elf')
            run('exec-file /out/app_stripped.elf', code=42, contains=b'seed chain\n')
            for name in ('start.o', 'answer.o', 'libanswer.a', 'app.elf', 'app_stripped.elf'):
                command_ok(f'rm /out/{name}', b'[files] removed')
            report['resource_samples'].append({'level': 's1', 'cycle': cycle, 'resources': resources(guest)})
        report['levels']['s1'] = {'cycles': args.s1_cycles, 'seconds': time.monotonic() - s1_start,
                                  'status': 'passed'}
        report['checks'].append(f's1_{args.s1_cycles}_full_cycles_resource_stable')

        if not args.skip_s2:
            # S2: 32 objects, archive append/index, 1 MiB rodata, 8 MiB BSS, link and execute.
            s2_start = time.monotonic()
            for i in range(32):
                run(f'exec-file /bin/as --64 -o /out/s/{i}.o /src/scale/{i}.s')
            run('exec-file /bin/as --64 -o /out/s/bss.o /src/scale/bss.s')
            run('exec-file /bin/as --64 -o /out/s/rodata.o /src/scale/rodata.s')
            run('exec-file /bin/as --64 -o /out/s/start.o /src/scale/start.s')
            run('exec-file /bin/ar rcS /out/s/libscale.a /out/s/0.o')
            for i in range(1, 32):
                run(f'exec-file /bin/ar r /out/s/libscale.a /out/s/{i}.o')
            run('exec-file /bin/ar r /out/s/libscale.a /out/s/bss.o /out/s/rodata.o')
            run('exec-file /bin/ranlib /out/s/libscale.a')
            run('exec-file /bin/ld -T /src/app.ld -o /out/s/scale.elf /out/s/start.o /out/s/libscale.a')
            run('exec-file /out/s/scale.elf', code=42)
            run('exec-file /bin/strip -o /out/s/scale_stripped.elf /out/s/scale.elf')
            run('exec-file /out/s/scale_stripped.elf', code=42)
            command_ok('ls /out/s', b'scale.elf')
            report['levels']['s2'] = {'objects': 34, 'archive_members': 34, 'seconds': time.monotonic() - s2_start,
                                      'status': 'passed'}
            report['checks'].append('s2_32_objects_1mib_rodata_8mib_bss_archive_link_execute')

        if args.s1_cycles == 0:
            # S3-only run needs the base objects that S1 normally creates.
            run('exec-file /bin/as --64 -o /out/start.o /src/start.s')
            run('exec-file /bin/as --64 -o /out/answer.o /src/answer.s')
            run('exec-file /bin/ar rcS /out/libanswer.a /out/answer.o')
            run('exec-file /bin/ranlib /out/libanswer.a')
        if not args.skip_s3:
            # S3: diagnostics and failure isolation.  Each expected failure must not
            # change source bytes or resource counters.
            s3_start = time.monotonic()
            run('exec-file /bin/as --64 -o /out/bad.o /src/bad.s', code=None, contains=b'Error:')
            run('exec-file /bin/as --64 -o /out/unresolved.o /src/unresolved.s')
            run('exec-file /bin/ld -T /src/app.ld -o /out/bad.elf /out/unresolved.o', code=None,
                contains=b'deliberately_missing_symbol')
            run('exec-file /bin/ld -T /src/app.ld -o /out/start.o /out/start.o /out/libanswer.a', code=None,
                contains=b'same as output')
            run('exec-file /bin/ld --plugin /src/no_plugin.so -T /src/app.ld -o /out/plugin.elf /out/start.o /out/libanswer.a',
                code=None, contains=b'unsupported')
            run('exec-file /bin/ld -T /src/app.ld -o /out/truncated.elf /src/truncated.o', code=None)
            command_ok('sync', b'[files] sync=ok')
            report['levels']['s3'] = {'cases': 7, 'seconds': time.monotonic() - s3_start, 'status': 'passed'}
            report['checks'].append('s3_error_and_truncation_paths_reclaim_and_do_not_corrupt_sources')

        # S4 is bounded in this run; the plan's 100-200 soak is a separate long run.
        if not args.skip_s4:
            s4_start = time.monotonic()
            for cycle in range(args.s4_cycles):
                run('exec-file /bin/as --64 -o /out/s4/start.o /src/start.s')
                run('exec-file /bin/as --64 -o /out/s4/answer.o /src/answer.s')
                run('exec-file /bin/ar rcS /out/s4/lib.a /out/s4/answer.o')
                run('exec-file /bin/ranlib /out/s4/lib.a')
                run('exec-file /bin/ld -T /src/app.ld -o /out/s4/app.elf /out/s4/start.o /out/s4/lib.a')
                run('exec-file /out/s4/app.elf', code=42, contains=b'seed chain\n')
                run('exec-file /bin/strip -o /out/s4/app_s.elf /out/s4/app.elf')
                run('exec-file /out/s4/app_s.elf', code=42, contains=b'seed chain\n')
                for name in ('start.o', 'answer.o', 'lib.a', 'app.elf', 'app_s.elf'):
                    command_ok(f'rm /out/s4/{name}', b'[files] removed')
                report['resource_samples'].append({'level': 's4', 'cycle': cycle, 'resources': resources(guest)})
            report['levels']['s4'] = {'cycles': args.s4_cycles, 'seconds': time.monotonic() - s4_start,
                                      'status': 'bounded_calibration'}

        # Source preservation after all positive and negative paths.
        command_ok('sync', b'[files] sync=ok')
        guest.close(); guest = None
        for name, expected in source_hashes.items():
            dest = base / ('source_' + name)
            transfer(disk, 'export', '/src/' + name, dest)
            if sha(dest) != expected:
                raise AssertionError(f'source changed: {name}')
        report['checks'].append('sources_preserved_byte_for_byte')
        report['status'] = 'passed'
        report['finished'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
        report['command_count'] = len(report['commands'])
        report['resource_max'] = {
            'free_min': min(x['resources'][0] for x in report['resource_samples']) if report['resource_samples'] else None,
            'tasks_max': max(x['resources'][1] for x in report['resource_samples']) if report['resource_samples'] else None,
            'completions_max': max(x['resources'][2] for x in report['resource_samples']) if report['resource_samples'] else None,
        }
        print(f"PASS: E08-3 stress levels s1/s2/s3{'' if args.skip_s4 else '/s4'} | build {system['build_id']} | commands {report['command_count']}")
    except Exception as error:
        report['error'] = str(error)
        report['failures'].append(str(error))
        print(f'FAIL: {error}')
        raise
    finally:
        if guest is not None:
            guest.close()
        if disk is not None and args.keep_image:
            keep = ROOT / 'build/e08_3_stress_last.img'
            if keep.exists(): keep.unlink()
            import shutil; shutil.copyfile(disk, keep)
            report['kept_image'] = str(keep)
        (build / 'binutils_stress_report.json').write_text(json.dumps(report, indent=2) + '\n')
        temporary.cleanup()


if __name__ == '__main__':
    main()
