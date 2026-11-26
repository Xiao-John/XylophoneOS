#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run a versioned program through a separately built GNU interpreter in native QEMU."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from glibc_d1_interpreter_entry_guest import INTERPRETER, describe
from glibc_d1_layout_guest import BIASES
from build_glibc_program import verify_elf
from boot_smoke import Guest
from glibc_g1_probe import clean_build_environment, tool_identity
from make_work_disk import create_fat32
from process_smoke import command, resources
from shell_launch_support import bind_system, relative_file, sha
from task_smoke import send_bytes
from work_disk import transfer
from xypm_sdk_profile import inspect_sdk


GCC_SHARED_SONAMES = ('libgcc_s.so.1', 'libm.so.0.1', 'libstdc++.so.6')
SHARED_CXX_MARKERS = (b'D2_SHARED_CXX_OK', b'D2_SHARED_CXX_TLS_DTOR', b'D2_SHARED_CXX_ATEXIT')


def bind_runtime_headers(build, runtime):
    files = {path.relative_to(build).as_posix() for path in (build / 'include').rglob('*') if path.is_file()}
    if not files or files != runtime['headers'].keys():
        raise ValueError('GCC shared header inventory differs from the manifest')
    for name, digest in runtime['headers'].items():
        if sha(relative_file(build, name)) != digest:
            raise ValueError('GCC shared closure header hash mismatch: ' + name)
    directories = [(build / name).resolve(strict=True) for name in runtime['include_directories']]
    if not directories or any(not path.is_dir() or not path.is_relative_to(build / 'include') for path in directories):
        raise ValueError('GCC shared include directory leaves the recorded header tree')
    return directories


def main():
    if not __debug__:
        raise SystemExit('run the diagnostic without Python optimization')
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'sdk-build', 'gnu-build', 'dash', 'dash-receipt', 'output'):
        parser.add_argument('--' + name, type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument('--case', choices=('c', 'cpp', 'unlisted', 'shared-cxx', 'shared-cxx-unlisted'), required=True)
    parser.add_argument('--pic-crt', type=lambda value: Path(value).resolve())
    parser.add_argument('--gcc-shared-build', type=lambda value: Path(value).resolve())
    parser.add_argument('--system-source', type=lambda value: Path(value).resolve(),
                        help='source tree recorded by the system manifest when using a prior exact image')
    args = parser.parse_args()
    shared_cxx = args.case.startswith('shared-cxx')
    if (args.case == 'cpp' or shared_cxx) and args.pic_crt is None:
        parser.error('the C++ case requires the GNU PIC CRT build output')
    if shared_cxx and args.gcc_shared_build is None:
        parser.error('the shared C++ case requires the GCC shared build')

    project = Path(__file__).resolve().parent.parent
    system = args.system
    system_source = args.system_source or project
    system_binding = bind_system(system, system_source)
    artifacts = args.gnu_build
    sources = project / 'tests/fixtures/glibc_d1'
    sysroot = args.sdk_build / 'sysroot'
    sdk_manifest = args.sdk_build / 'manifest.json'
    sdk = json.loads(sdk_manifest.read_bytes())
    sdk_binding = inspect_sdk('glibc', args.sdk_build)['binding']
    if json.loads(args.dash_receipt.read_bytes())['sha256'] != sha(args.dash):
        raise ValueError('the shell differs from the bound dash build')
    compiler_tools = {name: tool_identity('x86_64-elf-' + name)
                      for name in ('gcc', 'g++', 'ld', 'readelf', 'objcopy')}
    for name, tool in compiler_tools.items():
        if tool['sha256'] != sdk['tools']['x86_64-elf-' + name]['sha256']:
            raise ValueError('the selected tool differs from the C SDK build: ' + name)
    cc, cxx, ld, readelf, objcopy = (compiler_tools[name]['path']
                                   for name in ('gcc', 'g++', 'ld', 'readelf', 'objcopy'))
    flags = ['--sysroot=' + str(sysroot), '-O2', '-mno-red-zone', '-nostdinc', '-Wall', '-Wextra', '-Werror',
             '-isystem', sysroot / 'usr/include', '-isystem', sysroot / 'usr/lib/compiler-include',
             '-Wa,--noexecstack', '-Werror=trampolines']

    language = 'cpp' if args.case == 'cpp' or shared_cxx else 'c'
    unlisted = args.case.endswith('unlisted')
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    env, removed = clean_build_environment(os.environ)
    env['LC_ALL'] = 'C'
    report = {'status': 'failed', 'scope': 'private native GNU interpreter and a versioned application',
              'case': args.case, 'language': language, 'system_build_id': system_binding['build_id'],
              'commands': {}, 'tools': compiler_tools, 'sanitized_environment': removed, 'sdk_manifest_sha256': sha(sdk_manifest),
              'sdk_tree_sha256': sdk_binding['sdk_tree_sha256'],
              'system_manifest_sha256': sha(system / 'manifest.json'), 'iso_sha256': sha(system / 'xos-install.iso'),
              'dash_sha256': sha(args.dash), 'dash_receipt_sha256': sha(args.dash_receipt),
              'runner_sha256': sha(Path(__file__))}

    def run(name, command_args):
        argv = list(map(str, command_args))
        report['commands'][name] = argv
        with (out / (name + '.log')).open('w') as log:
            subprocess.run(argv, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)

    try:
        main, rtld, dependency, app, bootstrap, elf = (out / name for name in
            ('main.pie', 'interpreter.so', 'dependency.so', 'application.o', 'entry.o', 'entry.elf'))
        libc_image = artifacts / 'libc.so'
        rtld_image = artifacts / 'elf/ld.so'
        startup = artifacts / 'csu'
        native_files = artifacts / 'elf/xos_file_session.os'
        report['linked_originals'] = {str(path): sha(path) for path in (
            libc_image, rtld_image, native_files, *(startup / name for name in ('Scrt1.o', 'crti.o', 'crtn.o')))}
        app_source = sources / ('shared_cxx_application.cpp' if shared_cxx else f'interpreter_application.{language}')
        report['sources'] = {str(path): sha(path) for path in (app_source, sources / 'sysdep_start_bootstrap.cpp')}
        run('strip_debug_libc', [objcopy, '--strip-debug', libc_image, dependency])
        run('strip_debug_interpreter', [objcopy, '--strip-debug', rtld_image, rtld])
        extra = [] if language == 'c' else ['-nostdinc++', '-std=gnu++20']
        if language == 'cpp' and not shared_cxx:
            extra += ['-fno-exceptions', '-fno-rtti']
        compiler = cc if language == 'c' else cxx
        crt_begin, crt_end = [], []
        if language == 'cpp':
            crt_begin = [args.pic_crt / 'crtbeginS.o']
            crt_end = [args.pic_crt / 'crtendS.o']
            report['pic_crt'] = {path.name: sha(path) for path in (*crt_begin, *crt_end)}
        link = [ld, '--build-id=none', '--no-undefined', '-z', 'noexecstack', '-z', 'now', '-z', 'relro',
                '-z', 'max-page-size=8192', '-z', 'separate-code', '-rpath-link', artifacts / 'elf']
        dependency_bias = 0x140020000000
        dependencies = [('dependency', dependency, 'libc.so.0.1', dependency_bias, not shared_cxx)]
        app_libs = []
        if shared_cxx:
            gcc_build = args.gcc_shared_build
            runtime_manifest = gcc_build / 'manifest.json'
            runtime = json.loads(runtime_manifest.read_bytes())
            if (runtime['sdk_manifest_sha256'] != sha(sdk_manifest) or runtime['libc_sha256'] != sha(libc_image)
                    or runtime['interpreter_sha256'] != sha(rtld_image)):
                raise ValueError('the GCC shared closure belongs to a different glibc composition')
            report['linked_originals'][str(runtime_manifest)] = sha(runtime_manifest)
            for directory in bind_runtime_headers(gcc_build, runtime):
                extra += ['-isystem', directory]
            originals = []
            for index, soname in enumerate(GCC_SHARED_SONAMES, 1):
                lib_path = relative_file(gcc_build, 'lib/' + soname)
                if sha(lib_path) != runtime['artifacts'][soname]:
                    raise ValueError('GCC shared closure artifact hash mismatch: ' + soname)
                report['linked_originals'][str(lib_path)] = sha(lib_path)
                originals.append(lib_path)
                stripped = out / f'dependency-{index}.so'
                run('strip_' + str(index), [objcopy, '--strip-debug', lib_path, stripped])
                dependencies.append((f'dependency_{index}', stripped, soname,
                                     dependency_bias + index * 0x2000000, soname == 'libgcc_s.so.1'))
            module_source = sources / 'shared_cxx_dependency.cpp'
            api = sources / 'shared_cxx_exception.hpp'
            report['sources'].update({str(path): sha(path) for path in (module_source, api)})
            module_object, module = out / 'sample.o', out / 'sample.so'
            run('compile_module', [compiler, *extra, *flags, '-fPIC', '-c', module_source, '-o', module_object])
            link += ['--eh-frame-hdr', '-rpath-link', gcc_build / 'lib']
            gcc, math, std = originals
            atexit = relative_file(gcc_build, 'lib/atexit.oS')
            if sha(atexit) != runtime['artifacts']['atexit.oS']:
                raise ValueError('GNU atexit input hash mismatch')
            report['linked_originals'][str(atexit)] = sha(atexit)
            run('link_module', [*link, '-shared', '-soname', 'libsample.so', '-o', module, startup / 'crti.o',
                                *crt_begin, module_object, std, gcc, libc_image, rtld_image,
                                *crt_end, startup / 'crtn.o'])
            dependencies.append(('sample', module, 'libsample.so', dependency_bias + 0x8000000, False))
            app_libs = [atexit, module, std, gcc]
        run('compile_app', [compiler, *extra, *flags, '-fPIE', '-fno-builtin', '-c', app_source, '-o', app])
        run('link_app', [*link, '-pie', '-e', '_start', '--dynamic-linker', INTERPRETER[:-1].decode(), '-o', main,
                         startup / 'Scrt1.o', startup / 'crti.o', *crt_begin, app,
                         *app_libs, libc_image, *crt_end, startup / 'crtn.o'])
        run('elf_metadata', [readelf, '-hW', '-lW', '-dW', '-VW', main, rtld, *(item[1] for item in dependencies)])
        version = subprocess.check_output([readelf, '-dW', '-VW', main], env=env, text=True)
        needed = re.findall(r'Shared library: \[([^\]]+)\]', version)
        if not shared_cxx and (needed != ['libc.so.0.1'] or 'Name: GLIBC_2.44' not in version):
            raise RuntimeError('application did not link the versioned GNU libc')
        if shared_cxx:
            if set(needed) != {'libsample.so', 'libstdc++.so.6', 'libgcc_s.so.1', 'libc.so.0.1'} or not all(
                    name in version for name in ('Name: CXXABI_', 'Name: GLIBCXX_', 'Name: GLIBC_2.44')):
                raise RuntimeError('the shared application did not link the expected GNU versions')
            allowed = {'ld.so.1', *(item[2] for item in dependencies)}
            report['dependency_graph'] = {'main.pie': needed}
            for _, path, soname, _, _ in dependencies:
                tags = subprocess.check_output([readelf, '-dW', path], env=env, text=True)
                linked = re.findall(r'Shared library: \[([^\]]+)\]', tags)
                if f'Library soname: [{soname}]' not in tags or not set(linked) <= allowed or '(RUNPATH)' in tags or '(RPATH)' in tags:
                    raise RuntimeError('unexpected shared dependency or search path in ' + soname)
                report['dependency_graph'][soname] = linked
            if 'libgcc_s.so.1' not in report['dependency_graph']['libstdc++.so.6']:
                raise RuntimeError('libstdc++ did not link a shared unwinder')
        with (out / 'interpreter_plan.hpp').open('x') as header:
            report['images'] = {name: describe(path, name, bias, header) for name, path, bias in (
                ('main', main, BIASES[0]), ('interpreter', rtld, BIASES[1]),
                *((label, path, bias) for label, path, _, bias, _ in dependencies))}
            header.write('static constexpr linked_dependency linked_dependencies[] = {\n')
            for label, path, soname, _, omit in dependencies:
                header.write(f'    {{"/tests/{path.name}", "{soname}", {label}_bytes, {label}_digest, '
                             f'{label}_image.bias, {label}_span, {str(omit).lower()}}},\n')
            header.write('};\n')
            heap_pages, startup_seconds = (128, 90) if shared_cxx else (32, 30)
            report['startup_budget_seconds'] = startup_seconds
            report['early_heap_pages'] = heap_pages
            header.write(f'static constexpr u64 heap_pages = {heap_pages};\n')
            header.write(f'static constexpr u64 startup_budget_ns = {startup_seconds}000000000ULL;\n')
        headers = system / 'sdk/include'
        run('compile_bootstrap', [cxx, *flags, '-nostdinc++', '-std=gnu++20', '-ffreestanding', '-fno-pie',
                                  '-fno-exceptions', '-fno-rtti', '-fno-stack-protector', '-DD1_ACTUAL_INTERPRETER',
                                  '-I', headers, '-I', project / 'src/user/loader/glibc_d1', '-I',
                                  project / 'src/ports/glibc/sysdeps/xos', '-I', out, '-c',
                                  sources / 'sysdep_start_bootstrap.cpp', '-o', bootstrap])
        library = sysroot / 'usr/lib'
        native = system / 'sdk/lib'
        run('link_bootstrap', [ld, '--gc-sections', '-z', 'noexecstack', '-z', 'max-page-size=4096',
                               '--build-id=none', '-Map', out / 'link.map', '-T', sysroot / 'user.ld', '-o', elf,
                               library / 'xos_start.o', bootstrap, native_files,
                               '--start-group', native / 'libxos_loader.a', native / 'libxos.a',
                               library / 'libgcc.a', '--end-group'])
        report['bootstrap_sha256'] = sha(elf)
        report['bootstrap_program_headers'] = verify_elf(elf)
        data = out / 'input'
        data.write_bytes(b'ABCDEFGH\n')
        launch = out / 'app.sh'
        mode = 'unlisted' if unlisted else 'ordinary'
        launch.write_text(f'D1_ENTRY_ENV=verified /usr/bin/d1_entry {mode}\nrc=$?\n'
                          'printf "D1_DYNAMIC_STATUS=%s\\n" "$rc"\nexit "$rc"\n')
        with tempfile.TemporaryDirectory(prefix='xos_d1_native_application_') as folder:
            disk = Path(folder) / 'work.img'
            create_fat32(disk, 512)
            for name in ('/usr', '/usr/bin', '/tests'):
                transfer(disk, 'mkdir', name)
            for name, path in (('/usr/bin/d1_entry', elf), ('/usr/bin/dash', args.dash),
                               ('/tests/main.pie', main), ('/tests/interpreter.so', rtld),
                               *((f'/tests/{item[1].name}', item[1]) for item in dependencies),
                               ('/tests/input', data), ('/tests/app.sh', launch)):
                transfer(disk, 'import', name, path)
            guest = Guest(system / 'xos-install.iso', 'real_interpreter', work_disk=disk, qmp_enabled=False, log_dir=out)
            try:
                report['qemu_command'] = guest.command
                report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'],
                                                                 text=True).splitlines()[0]
                guest.expect(b'xos64> ', timeout=60)
                send_bytes(guest, b'run\r')
                guest.expect_supervisor(trace=True, timeout=60)
                command(guest, 'demo quiet', b'demo tasks')
                report['resources_before'] = resources(guest)
                started = time.monotonic()
                result = command(guest, 'dash /tests/app.sh', b'kind=exited code=', timeout=120)
                report['guest_command_seconds'] = round(time.monotonic() - started, 3)
                report['guest_output'] = result.decode(errors='replace')
                report['resources_after'] = resources(guest)
                markers = (b'D1_DYNAMIC_C_OK',) if language == 'c' else (b'D1_DYNAMIC_CPP_OK', b'D1_DYNAMIC_CPP_FINI')
                if shared_cxx:
                    markers = SHARED_CXX_MARKERS
                same_resources = report['resources_after'] == report['resources_before']
                exits = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', result)
                if unlisted:
                    missing = b'libgcc_s.so.1' if shared_cxx else b'libc.so.0.1'
                    if (any(marker in result for marker in markers) or b'D1_DYNAMIC_STATUS=127' not in result
                            or missing + b': cannot open shared object file' not in result
                            or exits != [b'127'] or not same_resources):
                        raise AssertionError('unlisted shared object did not meet the native refusal contract')
                elif (not all(marker in result for marker in markers) or b'D1_DYNAMIC_STATUS=0' not in result
                      or exits != [b'0'] or not same_resources):
                    raise AssertionError('externally linked application did not reach its normal native exit')
                elif shared_cxx and (any(result.count(marker) != 1 for marker in markers)
                                     or sorted(result.index(marker) for marker in markers) !=
                                     [result.index(marker) for marker in markers]):
                    raise AssertionError('the shared C++ exception and TLS teardown markers were out of order')
            finally:
                guest.close()
                report['serial_sha256'] = sha(out / 'real_interpreter_serial.log')
        if (bind_system(system, system_source) != system_binding or sha(sdk_manifest) != report['sdk_manifest_sha256']
                or sha(args.dash) != report['dash_sha256'] or sha(args.dash_receipt) != report['dash_receipt_sha256']
                or any(sha(Path(path)) != digest for group in ('linked_originals', 'sources')
                       for path, digest in report[group].items())
                or any(sha(args.pic_crt / path) != digest for path, digest in report.get('pic_crt', {}).items())):
            raise ValueError('a bound input changed during the native application run')
        if shared_cxx:
            bind_runtime_headers(gcc_build, runtime)
        report['status'] = 'passed_subset'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
