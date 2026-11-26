#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Diagnose the XOS shared/PIE build and compile the GNU rtld entry object."""

import argparse
import json
import os
from pathlib import Path
import shlex
import struct
import subprocess
import sys

from build_glibc_sdk import PORT, ROOT, inputs, sha
from glibc_g1_probe import clean_build_environment


SYSDEP_INVOCATION_ELF = (
    'dl-tunables.os', 'dl-sort-maps.os', 'dl-get-cpu-features.os', 'dl-misc.os',
    'dl-minimal.os', 'dl-printf.os', 'dl-trampoline.os',
    'dl-tlsdesc.os', 'dl-runtime.os', 'dl-profile.os', 'dl-tls.os', 'tlsdesc.os',
    'dl-lookup.os', 'dl-scope.os', 'dl-exception.os', 'dl-catch.os', 'dl-audit.os',
    'dl-thread_gscope_wait.os', 'getpid.os', '_exit.os',
)
SYSDEP_INVOCATION_LEAVES = (
    ('stdio-common', ('_fitoa_word', 'itoa-udigits')),
    ('string', ('stpcpy',)),
    ('setjmp', ('__longjmp',)),
    ('nptl', ('lowlevellock', 'xos_lll_futex', 'xos_wait_word')),
    ('csu', ('errno',)),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--jobs', type=int, choices=(1, 2), default=2)
    parser.add_argument('--initial-tp-fixture', action='store_true',
                        help='compile the native TP fixture with the GNU rtld build flags')
    parser.add_argument('--closure-tls-fixture', action='store_true',
                        help='compile the fixed-closure TLS fixture and its GNU runtime support')
    parser.add_argument('--gnu-relocation-fixture', action='store_true',
                        help='compile the real GNU relocation fixture and its native runtime support')
    parser.add_argument('--native-sysdep-fixture', action='store_true',
                        help='compile the GNU startup state fixture and its actual environment storage')
    parser.add_argument('--sysdep-invocation-fixture', action='store_true',
                        help='compile the GNU startup callback observer and actual GNU CPU/tunables support')
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
        if symbols.get('__xos_rtld_install_initial_tp') != 'U':
            raise RuntimeError('GNU rtld does not select the XOS initial thread handoff')

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
        rtld_heap = build / 'elf/xos_rtld_heap.os'
        rtld_allocator = build / 'elf/dl-minimal-malloc.os'
        rtld_startup = build / 'elf/xos_rtld_sysdep_start.os'
        rtld_invoke = build / 'elf/xos_rtld_sysdep_invoke.os'
        for path in (rtld_map, rtld_files, rtld_load, rtld_heap, rtld_allocator, rtld_startup, rtld_invoke):
            _, compilation = run('make_' + path.name, [*make_elf, path])
            if not any({'-fPIC', '-DSHARED', '-DMODULE_NAME=rtld'} <= set(line.split())
                       and line.split()[0].endswith('/cc') for line in compilation.splitlines()
                       if line.split()):
                raise RuntimeError('expected shared rtld module flags: ' + path.name)
        _, mapping_reference = run('dl_load_mapping_reference', [env['READELF'], '-rW', rtld_load])
        pins = ('__xos_rtld_open_pin', '__xos_rtld_read_pin', '__xos_rtld_pread_pin',
                '__xos_rtld_stat_pin', '__xos_rtld_close_pin')
        if not all(name in mapping_reference for name in (*pins, '__xos_rtld_map_fd', '__xos_rtld_release_image')):
            raise RuntimeError('upstream dl-load did not select the closed XOS I/O and mapping backend')
        _, loader_imports = run('dl_load_imports', [env['NM'], '-u', rtld_load])
        imports = {line.split()[-1] for line in loader_imports.splitlines()}
        if imports & {'__open64_nocancel', '__open64', '__read_nocancel', '__read', '__pread64_nocancel',
                      '__pread64', '__close_nocancel', '__close', '__fstat64_time64', '_dl_load_cache_lookup'}:
            raise RuntimeError('fixed startup dependencies still route through path or POSIX FD I/O')
        _, mapping_imports = run('native_mapping_imports', [env['NM'], '-u', rtld_map])
        if {line.split()[-1] for line in mapping_imports.splitlines()} != {'__xos_file_session_call_until', '__xos_rtld_check_entry', '__xos_rtld_heap_begin'}:
            raise RuntimeError('native rtld mapping unexpectedly depends on builtin libc or TLS')
        _, files_imports = run('native_files_imports', [env['NM'], '-u', rtld_files])
        if files_imports.strip():
            raise RuntimeError('native early files transport unexpectedly depends on another object')

        _, heap_imports = run('native_heap_imports', [env['NM'], '-u', rtld_heap])
        if heap_imports.strip():
            raise RuntimeError('native heap unexpectedly depends on libc or TLS')
        _, allocator_imports = run('rtld_allocator_imports', [env['NM'], '-u', rtld_allocator])
        allocator_symbols = {line.split()[-1] for line in allocator_imports.splitlines()}
        if '__xos_rtld_heap_grow' not in allocator_symbols or allocator_symbols & {'__mmap', 'mmap'}:
            raise RuntimeError('GNU minimal allocator did not select the XOS early heap')
        run('rtld_allocator_symbols', [env['NM'], rtld_allocator])
        _, startup_references = run('native_sysdep_symbols', [env['READELF'], '-sW', '-rW', rtld_startup])
        if not all(name in startup_references for name in
                   ('__xos_rtld_prepare_sysdep_start', '__xos_rtld_attach_entry_images',
                    '_rtld_local_ro', '_dl_argc', '_dl_argv', '_environ')):
            raise RuntimeError('native startup did not bind the GNU interpreter state and file session')
        _, invoke_references = run('native_invocation_symbols', [env['NM'], rtld_invoke])
        if not all(name in invoke_references for name in
                   (' T _dl_sysdep_start', ' T _dl_tunable_set_hwcaps', ' U __xos_rtld_prepare_sysdep_start',
                    ' U __GI___tunables_init', ' U _dl_sort_maps_init',
                    ' U _dl_x86_init_cpu_features')):
            raise RuntimeError('native startup invocation omitted GNU initialization or validated entry state')

        failure, reason = run('make_dl_sysdep', [*make_elf, build / 'elf/dl-sysdep.os'], allow_failure=True)
        if not failure or 'error: #error "XOS dynamic interpreter startup is not implemented"' not in reason:
            raise RuntimeError('expected the explicit XOS dynamic startup compile gate')
        for header in ('rtld-sizes.h', 'sem_t-align.h', 'cpu-features-offsets.h',
                       'features-offsets.h', 'link-defines.h', 'tlsdesc.h', 'rtld-offsets.h'):
            run('make_' + header, ['make', '-C', source / 'csu', 'objdir=' + str(build),
                                  '-j' + str(args.jobs), build / header])
        tls_objects = [build / 'elf' / name for name in
                       ('dl-tls.os', 'dl-tls_init_tp.os', 'dl-mutex.os')]
        for tls_object in tls_objects:
            _, compilation = run('make_' + tls_object.name, [*make_elf, tls_object])
            if not any({'-fPIC', '-DSHARED', '-DMODULE_NAME=rtld'} <= set(line.split())
                       and line.split()[0].endswith('/cc') for line in compilation.splitlines()
                       if line.split()):
                raise RuntimeError('expected shared rtld module flags: ' + tls_object.name)
        _, tls_imports = run('initial_tp_imports', [env['NM'], '-u', tls_objects[1]])
        if {line.split()[-1] for line in tls_imports.splitlines()} != {
                '_rtld_local', '___rtld_mutex_lock', '___rtld_mutex_unlock'}:
            raise RuntimeError('the native initial TP handoff depends on an unexpected runtime')
        run('initial_tls_relocations', [env['READELF'], '-rW', entry, *tls_objects])
        if args.closure_tls_fixture or args.gnu_relocation_fixture:
            support = ('dl-minimal.os', 'dl-catch.os', 'dl-exception.os', 'dl-printf.os',
                       'dl-tunables.os', 'getpid.os', '_exit.os')
            leaf_support = [('string', ('memmove', 'memset', 'strlen')),
                            ('stdio-common', ('_fitoa_word', 'itoa-udigits')),
                            ('setjmp', ('__longjmp',))]
            if args.gnu_relocation_fixture:
                support += ('dl-reloc.os', 'dl-lookup.os', 'dl-setup_hash.os', 'dl-audit.os',
                            'dl-misc.os', 'dl-scope.os', 'tlsdesc.os', 'dl-tlsdesc.os',
                            'dl-trampoline.os', 'dl-runtime.os', 'dl-get-cpu-features.os',
                            'dl-thread_gscope_wait.os', 'dl-profile.os')
                leaf_support.extend((('string', ('stpcpy', 'strcmp', 'memcmp')),
                                     ('misc', ('mprotect',)), ('csu', ('errno',)),
                                     ('nptl', ('lowlevellock', 'xos_lll_futex', 'xos_wait_word'))))
            for name in support:
                path = build / 'elf' / name
                _, compilation = run('make_' + name, [*make_elf, path])
                if not any({'-DPIC', '-DSHARED', '-DMODULE_NAME=rtld'} <= set(line.split())
                           for line in compilation.splitlines()):
                    raise RuntimeError('GNU runtime support did not compile as rtld: ' + name)
                tls_objects.append(path)
            for subdir, names in leaf_support:
                modules = ['rtld-' + name + '.os' for name in names]
                _, compilation = run('make_tls_support_' + subdir + '_' + names[0],
                                     ['make', '-C', source / subdir, '-f', 'Makefile',
                                      '-f', '../elf/rtld-Rules', 'rtld-all', 'subdir=' + subdir,
                                      'objdir=' + str(build), '-j' + str(args.jobs),
                                      'rtld-modules=' + ' '.join(modules)])
                for module in modules:
                    path = build / subdir / module
                    if not any('-DMODULE_NAME=rtld' in line.split() and str(path) in line.split()
                               for line in compilation.splitlines()):
                        raise RuntimeError('GNU rtld support result did not compile: ' + module)
                    tls_objects.append(path)
            for name in ('__xos_rtld_init_tls', '__xos_rtld_init_tls_templates'):
                if symbols.get(name) != 'T':
                    raise RuntimeError('GNU rtld initial TLS entry is absent: ' + name)

            shared_errno = [build / 'csu' / name for name in ('errno-loc.os', 'errno.os')]
            for path in shared_errno:
                _, compilation = run('make_libc_' + path.name,
                                     ['make', '-C', source / 'csu', 'objdir=' + str(build),
                                      '-j' + str(args.jobs), path])
                if not any({'-fPIC', '-DSHARED', '-DMODULE_NAME=libc'} <= set(line.split())
                           for line in compilation.splitlines()):
                    raise RuntimeError('libc errno result did not compile using the shared build')
            run('shared_libc_errno_relocations', [env['READELF'], '-rW', *shared_errno])
            tls_objects.extend(shared_errno)

        if args.sysdep_invocation_fixture:
            for name in SYSDEP_INVOCATION_ELF:
                path = build / 'elf' / name
                if path in tls_objects:
                    continue
                _, compilation = run('make_' + name, [*make_elf, path])
                if not any({'-DPIC', '-DSHARED', '-DMODULE_NAME=rtld'} <= set(line.split())
                           for line in compilation.splitlines()):
                    raise RuntimeError('GNU startup support did not compile as rtld: ' + name)
                tls_objects.append(path)

        if args.native_sysdep_fixture or args.sysdep_invocation_fixture:
            leaves = [('posix', 'environ')]
            if not args.gnu_relocation_fixture:
                leaves.append(('string', 'strcmp'))
            if args.sysdep_invocation_fixture:
                leaves.extend((subdir, name) for subdir, names in SYSDEP_INVOCATION_LEAVES for name in names)
            for subdir, name in leaves:
                module = 'rtld-' + name + '.os'
                path = build / subdir / module
                if path in tls_objects:
                    continue
                _, compilation = run('make_rtld_' + name,
                                     ['make', '-C', source / subdir, '-f', 'Makefile',
                                      '-f', '../elf/rtld-Rules', 'rtld-all', 'subdir=' + subdir,
                                      'objdir=' + str(build), '-j' + str(args.jobs),
                                      'rtld-modules=' + module])
                if not any('-DMODULE_NAME=rtld' in line.split() and str(path) in line.split()
                           for line in compilation.splitlines()):
                    raise RuntimeError('GNU rtld startup support did not compile: ' + module)
                tls_objects.append(path)

        for requested, prefix, name in (
                (args.initial_tp_fixture, 'initial_tp', 'initial_tls_guest.c'),
                (args.closure_tls_fixture, 'closure_tls', 'closure_tls_runtime.c'),
                (args.gnu_relocation_fixture, 'gnu_relocation', 'relocation_runtime.c'),
                (args.native_sysdep_fixture, 'native_sysdep', 'sysdep_start_state.c'),
                (args.sysdep_invocation_fixture, 'sysdep_invocation', 'sysdep_start_state.c')):
            if not requested:
                continue
            fixture_source = ROOT / 'tests/fixtures/glibc_d1' / name
            fixture = output / ('d1-' + prefix.replace('_', '-') + '-fixture.c')
            fixture.write_bytes(fixture_source.read_bytes())
            fixture_digest = sha(fixture)
            command, = (shlex.split(line) for line in
                        (output / 'make_dl-tls_init_tp.os.log').read_text().splitlines()
                        if line.startswith(env['CC'] + ' '))
            if Path(command[1]).name != 'dl-tls_init_tp.c':
                raise RuntimeError('cannot identify the GNU NPTL compile input')
            artifact = build / 'elf' / ('d1-' + prefix.replace('_', '-') + '-fixture.o')
            command[1] = fixture
            command[command.index('-o') + 1] = artifact
            fixture_flags = ['-DD1_SYSDEP_INVOKE'] if prefix == 'sysdep_invocation' else []
            run('compile_' + prefix + '_fixture', [*command[:command.index('-MD')], '-Werror',
                                                    *fixture_flags], cwd=source / 'elf')
            if sha(fixture) != fixture_digest or sha(fixture_source) != fixture_digest:
                raise RuntimeError('the GNU rtld fixture changed during compilation')
            tls_objects.append(artifact)
            report[prefix + '_fixture_sha256'] = fixture_digest
        failure, _ = run('make_ld_so', [*make_elf, build / 'elf/ld.so'], allow_failure=True)
        if not failure or (build / 'elf/ld.so').exists():
            raise RuntimeError('ld.so unexpectedly linked despite the startup gate')

        if (sha(archive) != preparation['source_sha256'] or inputs() != preparation['inputs']
                or sha(preparation_manifest) != prepared_hash
                or sha(Path(__file__)) != report['probe_sha256']
                or any(sha(Path(tool['path'])) != tool['sha256'] for tool in tools.values())):
            raise RuntimeError('source preparation or configured tools changed during the diagnostic')
        report.update(status='rtld_entry_compiled_startup_blocked', artifacts={
            str(path.relative_to(output)): sha(path) for path in
            (entry, native_entry, rtld_map, rtld_files, rtld_load, rtld_heap, rtld_allocator,
             rtld_startup, rtld_invoke, *tls_objects)})
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print('GNU rtld entry object compiled; the native startup gate still blocks ld.so')


if __name__ == '__main__':
    main()
