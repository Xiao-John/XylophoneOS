# SPDX-License-Identifier: Apache-2.0
"""Run genuine XOS-hosted GNU tools; host inspection never executes the Seed."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from make_work_disk import create_fat32
from work_disk import transfer
from e08_storage_smoke import boot
from process_smoke import command, resources
from toolchain import tool


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed-manifest', type=Path, required=True)
    args = parser.parse_args()
    seed_path = args.seed_manifest.resolve()
    seed = json.loads(seed_path.read_text())
    build = ROOT / 'build'
    system = json.loads((build / 'manifest.json').read_text())
    sdk = ROOT / seed['sdk_manifest']
    if sha(sdk) != seed['sdk_manifest_sha256']:
        raise AssertionError('Seed SDK provenance differs from its manifest')
    # A new system build can add fixtures/docs; every runtime artifact must still
    # match the SDK that was actually linked into these Seed executables.
    for name in ('crt0_posix.o', 'lib/libxos.a', 'lib/libxos_loader.a', 'lib/libc.a', 'lib/libm.a', 'user.ld'):
        if sha(sdk.parent / name) != sha(build / 'sdk' / name):
            raise AssertionError(f'Seed needs relink against current runtime: {name}')
    report = {'build_id': system['build_id'], 'seed_manifest_sha256': sha(seed_path),
              'seed_manifest': str(seed_path.relative_to(ROOT)), 'checks': [],
              'commands': [], 'artifacts': {}, 'status': 'failed'}
    guest = None
    fixtures = ROOT / 'tests/fixtures/binutils'
    try:
        with tempfile.TemporaryDirectory(prefix='xos_binutils_') as folder:
            temporary = Path(folder)
            disk = temporary / 'test.img'
            create_fat32(disk, 512)
            for path in ('/bin', '/src', '/out', '/tmp'):
                transfer(disk, 'mkdir', path)
            for name in ('as', 'ld', 'ar', 'ranlib', 'strip'):
                item = seed['tools'][name]
                source = seed_path.parent / 'install' / item['path']
                if sha(source) != item['sha256']:
                    raise AssertionError(f'Seed tool changed: {name}')
                transfer(disk, 'import', '/bin/' + name, source)
                report['artifacts']['seed_' + name] = {'sha256': item['sha256'], 'bytes': source.stat().st_size}
            transfer(disk, 'import', '/bin/runtime_probe.elf', build / 'user_runtime_probe.image.elf')
            source_hashes = {}
            for path in sorted(fixtures.iterdir()):
                if path.is_file():
                    transfer(disk, 'import', '/src/' + path.name, path)
                    source_hashes[path.name] = sha(path)

            guest = boot(disk, 'binutils_smoke')
            baseline = resources(guest)

            def run(line, code=0, contains=None):
                started = time.monotonic()
                output = command(guest, line, b'[wait] pid=', timeout=180)
                match = re.search(rb'kind=exited code=(-?\d+)', output)
                if match is None or (int(match[1]) != code if code is not None else int(match[1]) == 0):
                    raise AssertionError(output[-4000:])
                diagnostic = output.split(b'\n', 1)[1] if b'\n' in output else b''
                if contains is not None and contains not in diagnostic:
                    raise AssertionError(output[-4000:])
                if resources(guest) != baseline:
                    raise AssertionError('Seed tool leaked physical pages/tasks/completions')
                report['commands'].append({'line': line, 'exit_code': int(match[1]),
                                           'host_elapsed_seconds': time.monotonic() - started})
                return output

            for name in ('as', 'ld', 'ar', 'ranlib', 'strip'):
                run('exec-file /bin/' + name + ' --version', contains=b'2.47')
            report['checks'].append('five_real_gnu_seed_tools_identify_themselves_and_reclaim_resources')
            for iteration in range(2):
                run('exec-file /bin/as --64 -o /out/start.o /src/start.s')
                run('exec-file /bin/as --64 -o /out/answer.o /src/answer.s')
                if iteration:
                    command(guest, 'rm /out/libanswer.a', b'[files] removed')
                run('exec-file /bin/ar rcS /out/libanswer.a /out/answer.o')
                run('exec-file /bin/runtime_probe.elf archive-index /out/libanswer.a no',
                    contains=b'archive-index=absent')
                run('exec-file /bin/ranlib /out/libanswer.a')
                run('exec-file /bin/runtime_probe.elf archive-index /out/libanswer.a yes',
                    contains=b'archive-index=present')
                run('exec-file /bin/ld -T /src/app.ld -o /out/start.o /out/start.o /out/libanswer.a',
                    code=None, contains=b'same as output')
                run('exec-file /bin/ld -T /src/app.ld -o /out/app.elf /out/start.o /out/libanswer.a')
                run('exec-file /out/app.elf', code=42, contains=b'seed chain\n')
                run('exec-file /bin/strip -o /out/app_stripped.elf /out/app.elf')
                run('exec-file /out/app_stripped.elf', code=42, contains=b'seed chain\n')
                report['checks'].append(f'guest_assemble_archive_index_link_strip_execute_reclaim_{iteration}')
            run('exec-file /bin/as --64 -o /out/bad.o /src/bad.s', code=None, contains=b'Error:')
            run('exec-file /bin/as --64 -o /out/unresolved.o /src/unresolved.s')
            run('exec-file /bin/ld -T /src/app.ld -o /out/bad.elf /out/unresolved.o',
                code=None, contains=b'deliberately_missing_symbol')
            run('exec-file /bin/ld --plugin /src/no_plugin.so -T /src/app.ld -o /out/plugin.elf /out/start.o /out/libanswer.a',
                code=None, contains=b'unsupported')
            report['checks'].append('assembler_and_linker_diagnostics_nonzero_and_reclaimed')
            command(guest, 'sync', b'[files] sync=ok')
            guest.close()
            guest = None
            for name, expected in source_hashes.items():
                destination = temporary / ('original_' + name)
                transfer(disk, 'export', '/src/' + name, destination)
                if sha(destination) != expected:
                    raise AssertionError(f'guest tools changed source: {name}')
            report['checks'].append('all_saved_sources_preserved_byte_for_byte')
            for name in ('start.o', 'answer.o', 'libanswer.a', 'app.elf', 'app_stripped.elf'):
                destination = build / ('binutils_' + name)
                exported = temporary / ('generated_' + name)
                transfer(disk, 'export', '/out/' + name, exported)
                shutil.copyfile(exported, destination)
                report['artifacts'][name] = {'sha256': sha(destination), 'bytes': destination.stat().st_size}
            for name in ('app.elf', 'app_stripped.elf'):
                output = subprocess.check_output([tool('readelf'), '-h', '-l', '-s', str(build / ('binutils_' + name))], text=True)
                (build / ('binutils_' + name + '.readelf.txt')).write_text(output)
                if 'EXEC (Executable file)' not in output or 'INTERP' in output or re.search(r'\bRWE\b', output):
                    raise AssertionError('guest ELF format/protection contract violated')
                if name == 'app.elf' and 'answer' not in output:
                    raise AssertionError('archive member was not linked')
                if name == 'app_stripped.elf' and 'Symbol table' in output:
                    raise AssertionError('strip did not strip symbol table')
            output = subprocess.check_output([tool('nm'), '--print-armap', str(build / 'binutils_libanswer.a')], text=True)
            (build / 'binutils_archive_symbols.txt').write_text(output)
            if 'answer in answer.o' not in output:
                raise AssertionError('archive index absent')
            report['checks'].append('host_static_inspection_confirms_elf_archive_index_and_strip')
            guest = boot(disk, 'binutils_reboot')
            baseline = resources(guest)
            run('exec-file /out/app_stripped.elf', code=42, contains=b'seed chain\n')
            report['checks'].append('guest_generated_stripped_elf_survives_synced_reboot')
            report['status'] = 'passed'
            print(f"PASS: {len(report['checks'])} E08-3 groups | build {system['build_id']}")
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if guest is not None:
            guest.close()
        (build / 'binutils_smoke_report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
