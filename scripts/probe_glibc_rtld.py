#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Diagnose the XOS shared/PIE build and compile the GNU rtld entry object."""

import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

from build_glibc_sdk import PORT, ROOT, inputs, sha
from glibc_g1_probe import clean_build_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--jobs', type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True)
    env, _ = clean_build_environment(os.environ)
    env.update(CONFIG_SITE='/dev/null', LC_ALL='C')
    report = {'status': 'failed', 'scope': 'rtld diagnostic, no SDK or guest qualification', 'steps': []}

    def run(name, command, *, cwd=output, allow_failure=False):
        log = output / (name + '.log')
        with log.open('w') as stream:
            result = subprocess.run(command, env=env, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
        report['steps'].append({'name': name, 'command': list(map(str, command)),
                                'exit_code': result.returncode, 'log_sha256': sha(log)})
        if result.returncode and not allow_failure:
            raise RuntimeError(name + ' failed; see ' + str(log))
        return result.returncode, log.read_text(errors='replace')

    try:
        prepared = output / 'prepared'
        run('prepare', [sys.executable, ROOT / 'scripts/build_glibc_sdk.py', '--archive', archive,
                        '--output', prepared, '--prepare-only'])
        preparation_manifest = prepared / 'manifest.json'
        prepared_hash = sha(preparation_manifest)
        preparation = json.loads(preparation_manifest.read_bytes())
        if (preparation['status'] != 'configured'
                or preparation['source_verification']['status'] != 'upstream_signature_verified'):
            raise RuntimeError('source preparation is incomplete or unauthenticated')
        lock = json.loads((PORT / 'source_lock.json').read_bytes())
        source = prepared / ('glibc-' + lock['version'])
        tools = preparation['tools']
        report.update(source_sha256=preparation['source_sha256'], preparation_manifest_sha256=prepared_hash,
                      source_verification_report_sha256=preparation['source_verification_report_sha256'],
                      probe_sha256=sha(Path(__file__)), tools=tools)
        env.update(CC=str(prepared / 'cc'), CXX=str(prepared / 'cxx'), CFLAGS='-O2 -g -mno-red-zone')
        for tool in ('AS', 'LD', 'AR', 'NM', 'RANLIB', 'OBJCOPY', 'OBJDUMP', 'READELF'):
            env[tool] = tools['x86_64-elf-' + tool.lower()]['path']

        probe_source = output / 'entry.c'
        probe_object = output / 'entry.o'
        probe_source.write_text('int xos_d1_link_probe (void) { return 17; }\n')
        run('compile_probe', [env['CC'], '-fPIC', '-c', probe_source, '-o', probe_object])
        drivers = report['driver_elf_types'] = {}
        for name, options in (
                ('driver_shared', ['-shared']),
                ('explicit_shared', ['-shared', '-Wl,-shared']),
                ('driver_pie', ['-pie', '-Wl,--no-dynamic-linker'])):
            image = output / (name + '.elf')
            run(name, [env['CC'], '-nostdlib', *options, '-Wl,-e,xos_d1_link_probe', '-o', image, probe_object])
            _, inspection = run(name + '_readelf', [env['READELF'], '-hW', '-lW', image])
            kind = next(line.split(':', 1)[1].strip() for line in inspection.splitlines()
                        if line.strip().startswith('Type:'))
            drivers[name] = kind
        if (drivers['explicit_shared'] != 'DYN (Shared object file)'
                or drivers['driver_pie'] != 'DYN (Position-Independent Executable file)'):
            raise RuntimeError('diagnostic shared or PIE link produced an unexpected ELF type')

        build = output / 'shared'
        build.mkdir()
        run('configure_shared', [source / 'configure', '--build=' + preparation['host_build_triplet'],
                                 '--host=x86_64-unknown-xos', '--prefix=/usr', '--disable-werror', '--enable-shared',
                                 '--enable-default-pie', '--disable-multi-arch', '--disable-mathvec',
                                 '--without-selinux', '--disable-nscd'], cwd=build)
        features = (build / 'config.make').read_text().splitlines()
        if not {'build-shared = yes', 'build-pie-default = yes'} <= set(features):
            raise RuntimeError('configure did not select shared libc and default PIE')
        (build / 'configparms').write_text('ASFLAGS += -Wa,--divide\n')

        make_elf = ['make', '-C', source / 'elf', 'objdir=' + str(build), '-j' + str(args.jobs)]
        entry = build / 'elf/rtld.os'
        _, compilation = run('make_rtld', [*make_elf, entry])
        if not any({'rtld.c', '-fPIC', '-DSHARED', '-DMODULE_NAME=rtld'} <= set(line.split())
                   for line in compilation.splitlines()):
            raise RuntimeError('expected the upstream PIC rtld.c compile command')
        header = entry.read_bytes()[:64]
        if header[:7] != b'\x7fELF\x02\x01\x01' or struct.unpack_from('<HH', header, 16) != (1, 62):
            raise RuntimeError('rtld entry object is not x86-64 ET_REL')
        run('rtld_readelf', [env['READELF'], '-hW', '-rW', entry])
        _, symbol_output = run('rtld_symbols', [env['NM'], entry])
        symbols = dict(line.split()[-2:][::-1] for line in symbol_output.splitlines() if line.strip())
        if any(symbols.get(name) != kind for name, kind in (
                ('_start', 'T'), ('_dl_start', 't'), ('_dl_start_user', 'T'), ('_dl_sysdep_start', 'U'))):
            raise RuntimeError('expected rtld entry and unresolved XOS startup handoff')

        native_entry = build / 'elf/xos_rtld_entry.os'
        _, native_compilation = run('make_native_entry', [*make_elf, native_entry])
        if not any({'-fPIC', '-DSHARED', '-DMODULE_NAME=rtld'} <= set(line.split())
                   and line.split()[0].endswith('/cc') for line in native_compilation.splitlines()
                   if line.split()):
            raise RuntimeError('expected the native entry checker to compile in the shared rtld module')
        _, native_symbols = run('native_entry_symbols', [env['NM'], native_entry])
        if '__xos_rtld_check_entry' not in native_symbols:
            raise RuntimeError('missing native entry checker')
        _, undefined = run('native_entry_undefined', [env['NM'], '-u', native_entry])
        if undefined.strip():
            raise RuntimeError('native entry checker unexpectedly depends on another object')
        run('native_entry_readelf', [env['READELF'], '-hW', '-rW', native_entry])

        rtld_map = build / 'elf/xos_rtld_mapping.os'
        rtld_files = build / 'elf/xos_file_session.os'
        rtld_load = build / 'elf/dl-load.os'
        for path in (rtld_map, rtld_files, rtld_load):
            _, compilation = run('make_' + path.name, [*make_elf, path])
            if not any({'-fPIC', '-DSHARED', '-DMODULE_NAME=rtld'} <= set(line.split())
                       and line.split()[0].endswith('/cc') for line in compilation.splitlines()
                       if line.split()):
                raise RuntimeError('expected shared rtld module flags: ' + path.name)
        _, mapping_reference = run('dl_load_mapping_reference', [env['READELF'], '-rW', rtld_load])
        if not all(name in mapping_reference for name in ('__xos_rtld_map_fd', '__xos_rtld_release_image')):
            raise RuntimeError('upstream dl-load did not select the XOS mapping backend')
        _, mapping_imports = run('native_mapping_imports', [env['NM'], '-u', rtld_map])
        if {line.split()[-1] for line in mapping_imports.splitlines()} != {'__xos_file_session_call'}:
            raise RuntimeError('native rtld mapping unexpectedly depends on builtin libc or TLS')
        _, files_imports = run('native_files_imports', [env['NM'], '-u', rtld_files])
        if files_imports.strip():
            raise RuntimeError('native early files transport unexpectedly depends on another object')

        failure, reason = run('make_dl_sysdep', [*make_elf, build / 'elf/dl-sysdep.os'], allow_failure=True)
        if not failure or 'error: #error "XOS dynamic interpreter startup is not implemented"' not in reason:
            raise RuntimeError('expected the explicit XOS dynamic startup compile gate')
        for header in ('rtld-sizes.h', 'sem_t-align.h', 'cpu-features-offsets.h',
                       'features-offsets.h', 'link-defines.h', 'tlsdesc.h', 'rtld-offsets.h'):
            run('make_' + header, ['make', '-C', source / 'csu', 'objdir=' + str(build),
                                  '-j' + str(args.jobs), build / header])
        failure, _ = run('make_ld_so', [*make_elf, build / 'elf/ld.so'], allow_failure=True)
        if not failure or (build / 'elf/ld.so').exists():
            raise RuntimeError('ld.so unexpectedly linked despite the startup gate')

        if (sha(archive) != preparation['source_sha256'] or inputs() != preparation['inputs']
                or sha(preparation_manifest) != prepared_hash
                or sha(Path(__file__)) != report['probe_sha256']
                or any(sha(Path(tool['path'])) != tool['sha256'] for tool in tools.values())):
            raise RuntimeError('source preparation or configured tools changed during the diagnostic')
        report.update(status='rtld_entry_compiled_startup_blocked', artifacts={str(path.relative_to(output)): sha(path) for path in (entry, native_entry, rtld_map, rtld_files, rtld_load)})
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print('GNU rtld entry object compiled; the native startup gate still blocks ld.so')


if __name__ == '__main__':
    main()
