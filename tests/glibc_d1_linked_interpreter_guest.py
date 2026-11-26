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

from glibc_d1_interpreter_entry_guest import INTERPRETER, describe
from glibc_d1_layout_guest import BIASES
from build_glibc_program import verify_elf
from boot_smoke import Guest
from glibc_g1_probe import clean_build_environment, tool_identity
from make_work_disk import create_fat32
from process_smoke import command, resources
from shell_launch_support import bind_system, sha
from task_smoke import send_bytes
from work_disk import transfer
from xypm_sdk_profile import inspect_sdk


def main():
    if not __debug__:
        raise SystemExit('run the diagnostic without Python optimization')
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'sdk-build', 'gnu-build', 'dash', 'dash-receipt', 'output'):
        parser.add_argument('--' + name, type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument('--case', choices=('c', 'cpp', 'unlisted'), required=True)
    parser.add_argument('--pic-crt', type=lambda value: Path(value).resolve())
    args = parser.parse_args()
    if args.case == 'cpp' and args.pic_crt is None:
        parser.error('the C++ case requires the GNU PIC CRT build output')

    project = Path(__file__).resolve().parent.parent
    system = args.system
    system_binding = bind_system(system)
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

    language = 'cpp' if args.case == 'cpp' else 'c'
    unlisted = args.case == 'unlisted'
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
        report['sources'] = {str(path): sha(path) for path in (
            sources / f'interpreter_application.{language}', sources / 'sysdep_start_bootstrap.cpp')}
        run('strip_debug_libc', [objcopy, '--strip-debug', libc_image, dependency])
        run('strip_debug_interpreter', [objcopy, '--strip-debug', rtld_image, rtld])
        extra = [] if language == 'c' else ['-nostdinc++', '-std=gnu++20', '-fno-exceptions', '-fno-rtti']
        compiler = cc if language == 'c' else cxx
        run('compile_app', [compiler, *flags, *extra, '-fPIE', '-fno-builtin', '-c',
                            sources / f'interpreter_application.{language}', '-o', app])
        crt_begin, crt_end = [], []
        if language == 'cpp':
            crt_begin = [args.pic_crt / 'crtbeginS.o']
            crt_end = [args.pic_crt / 'crtendS.o']
            report['pic_crt'] = {path.name: sha(path) for path in (*crt_begin, *crt_end)}
        run('link_app', [ld, '-pie', '-e', '_start', '--build-id=none', '--no-undefined',
                         '-z', 'noexecstack', '-z', 'now', '-z', 'relro', '-z', 'max-page-size=8192',
                         '-z', 'separate-code', '--dynamic-linker', INTERPRETER[:-1].decode(),
                         '-rpath-link', artifacts / 'elf', '-o', main,
                         startup / 'Scrt1.o', startup / 'crti.o', *crt_begin, app,
                         libc_image, *crt_end, startup / 'crtn.o'])
        run('elf_metadata', [readelf, '-hW', '-lW', '-dW', '-VW', main, rtld, dependency])
        version = subprocess.check_output([readelf, '-dW', '-VW', main], env=env, text=True)
        needed = re.findall(r'Shared library: \[([^\]]+)\]', version)
        if needed != ['libc.so.0.1'] or 'Name: GLIBC_2.44' not in version:
            raise RuntimeError('application did not link the versioned GNU libc')
        with (out / 'interpreter_plan.hpp').open('x') as header:
            report['images'] = {name: describe(path, name, bias, header) for name, path, bias in (
                ('main', main, BIASES[0]), ('interpreter', rtld, BIASES[1]),
                ('dependency', dependency, 0x140020000000))}
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
                               ('/tests/dependency.so', dependency), ('/tests/input', data), ('/tests/app.sh', launch)):
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
                result = command(guest, 'dash /tests/app.sh', b'kind=exited code=', timeout=120)
                report['guest_output'] = result.decode(errors='replace')
                report['resources_after'] = resources(guest)
                markers = (b'D1_DYNAMIC_C_OK',) if language == 'c' else (b'D1_DYNAMIC_CPP_OK', b'D1_DYNAMIC_CPP_FINI')
                same_resources = report['resources_after'] == report['resources_before']
                exits = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', result)
                if unlisted:
                    if (any(marker in result for marker in markers) or b'D1_DYNAMIC_STATUS=127' not in result
                            or b'cannot open shared object file' not in result or exits != [b'127'] or not same_resources):
                        raise AssertionError('unlisted shared object did not meet the native refusal contract')
                elif (not all(marker in result for marker in markers) or b'D1_DYNAMIC_STATUS=0' not in result
                      or exits != [b'0'] or not same_resources):
                    raise AssertionError('externally linked application did not reach its normal native exit')
            finally:
                guest.close()
                report['serial_sha256'] = sha(out / 'real_interpreter_serial.log')
        if (bind_system(system) != system_binding or sha(sdk_manifest) != report['sdk_manifest_sha256']
                or sha(args.dash) != report['dash_sha256'] or sha(args.dash_receipt) != report['dash_receipt_sha256']
                or any(sha(Path(path)) != digest for group in ('linked_originals', 'sources')
                       for path, digest in report[group].items())
                or any(sha(args.pic_crt / path) != digest for path, digest in report.get('pic_crt', {}).items())):
            raise ValueError('a bound input changed during the native application run')
        report['status'] = 'passed_subset'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
