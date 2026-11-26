#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Boot the GNU initial TLS path with two authenticated native DSO pins."""
import argparse
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from boot_smoke import Guest
from build_glibc_program import verify_elf
from glibc_d1_initial_tp_guest import bind_rtld_inputs
from glibc_d1_layout_guest import BIASES, PHDR
from glibc_g1_probe import clean_build_environment, tool_identity
from make_work_disk import create_fat32
from process_smoke import command, resources
from shell_launch_support import bind_system, sha, write_report
from task_smoke import send_bytes
from work_disk import transfer
from xypm_format import load_json
from xypm_sdk_profile import verify_profile

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/glibc_d1'
FIXTURE = FIXTURES / 'closure_tls_runtime.c'
OVERLAY = ROOT / 'src/ports/glibc/sysdeps/xos'
PAGE = 4096
SUPPORT = ('elf/dl-tls.os', 'elf/dl-tls_init_tp.os', 'elf/dl-mutex.os',
           'elf/dl-minimal.os', 'elf/dl-minimal-malloc.os', 'elf/dl-catch.os',
           'elf/dl-exception.os', 'elf/dl-printf.os', 'elf/dl-tunables.os',
           'elf/getpid.os', 'elf/_exit.os', 'elf/xos_rtld_heap.os',
           'elf/xos_rtld_entry.os', 'elf/xos_rtld_mapping.os', 'elf/xos_file_session.os',
           'string/rtld-memmove.os', 'string/rtld-memset.os', 'string/rtld-strlen.os',
           'stdio-common/rtld-_fitoa_word.os', 'stdio-common/rtld-itoa-udigits.os',
           'setjmp/rtld-__longjmp.os')
SUCCESS = b'D1_CLOSURE_TLS_OK modules=2 tdata=checked tbss=zero dtv=1 tp=preserved'
OOM = b'XOS rtld: cannot allocate initial TLS slotinfo'


def describe(path, index, alignment, value, plan):
    data = path.read_bytes()
    if (data[:7] != b'\x7fELF\x02\x01\x01' or struct.unpack_from('<HH', data, 16) != (3, 62)):
        raise ValueError('dependency must be x86-64 ET_DYN')
    phoff = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    if size != PHDR.size or not (0 < count <= 64) or phoff + count * size > len(data):
        raise ValueError('unexpected dependency program headers')
    table = [PHDR.unpack_from(data, phoff + i * size) for i in range(count)]
    tls, = [header for header in table if header[0] == 7]
    loads = [header for header in table if header[0] == 1 and header[6]]
    _, flags, offset, address, _, filesz, memsz, align = tls
    if (flags != 4 or filesz < 3 or memsz - filesz < 129 or align != alignment
            or data[offset:offset + 3] != bytes((value, 0x3c, 0x19))
            or not any(p[1] & 4 and p[2] <= offset <= offset + filesz <= p[2] + p[5]
                       and p[3] + offset - p[2] == address for p in loads)):
        raise ValueError('PT_TLS does not describe the expected file-backed template')
    span = (max(p[3] + p[6] for p in loads) + PAGE - 1) & -PAGE
    digest = sha(path)
    octets = ','.join(hex(octet) for octet in bytes.fromhex(digest))
    plan.write(f'static constexpr u8 digest_{index}[] = {{{octets}}};\n')
    return {'sha256': digest, 'bias': BIASES[index], 'bytes': len(data), 'span': span,
            'tls_file_offset': offset, 'tls_vaddr': address, 'tls_file_bytes': filesz,
            'tls_memory_bytes': memsz, 'tls_alignment': align}


def build(args, report, rtld):
    output, proof = args.output, args.rtld_proof
    sysroot = args.sdk_build / 'sysroot'
    names = ('gcc', 'g++', 'as', 'ld', 'readelf', 'objcopy', 'nm')
    tools = {name: tool_identity('x86_64-elf-' + name) for name in names}
    for name, tool in tools.items():
        if tool['sha256'] != rtld['tools']['x86_64-elf-' + name]['sha256']:
            raise ValueError('rtld tool changed: ' + name)
    report['tools'] = tools
    tool_dir = output / 'tools'
    tool_dir.mkdir()
    for name in ('as', 'ld'):
        (tool_dir / name).symlink_to(tools[name]['path'])
    env, report['sanitized_environment'] = clean_build_environment(os.environ)
    env['LC_ALL'] = 'C'

    def run(stage, name, *argv):
        command_line = [tools[name]['path'], *map(str, argv)]
        report['commands'][stage] = command_line
        with (output / (stage + '.log')).open('w') as log:
            subprocess.run(command_line, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)

    flags = ['-B' + str(tool_dir) + '/', '--sysroot=' + str(sysroot), '-nostdinc',
             '-isystem', sysroot / 'usr/include', '-isystem', sysroot / 'usr/lib/compiler-include',
             '-O2', '-mno-red-zone', '-ffreestanding', '-fno-builtin',
             '-fno-stack-protector', '-Wall', '-Wextra', '-Werror']
    dependencies = report['dependencies'] = {}
    with (output / 'closure_tls_plan.hpp').open('x') as plan:
        for index, (alignment, value) in enumerate(((64, 0x51), (256, 0xa7))):
            name = f'libtls{index + 1}.so'
            obj, dso = output / (name + '.o'), output / name
            run('compile_' + name, 'gcc', *flags, '-fPIC', f'-DD1_TLS_ALIGNMENT={alignment}',
                f'-DD1_TLS_VALUE={value}', '-c', FIXTURES / 'closure_tls_dependency.c', '-o', obj)
            run('link_' + name, 'ld', '-shared', '-e', 'd1_dependency', '-soname', name,
                '-z', 'max-page-size=8192', '-z', 'separate-code', '-z', 'noexecstack',
                '--no-undefined', '--build-id=none', '-o', dso, obj)
            run('inspect_' + name, 'readelf', '-hW', '-lW', '-dW', '-rW', dso)
            dependencies[name] = describe(dso, index, alignment, value, plan)
        plan.write('static constexpr dependency dependencies[] = {\n')
        for index, (name, info) in enumerate(dependencies.items()):
            plan.write(f'    {{"/tests/{name}", "{name}", {info["bias"]}, {info["bytes"]}, '
                       f'{info["span"]}, digest_{index}}},\n')
        plan.write('};\n')

    bootstrap, elf = output / 'bootstrap.o', output / 'closure_tls.elf'
    run('compile_bootstrap', 'g++', *flags, '-fno-pie', '-fno-exceptions', '-fno-rtti',
        '-nostdinc++', '-std=gnu++20', '-I', args.system / 'sdk/include',
        '-I', OVERLAY, '-I', output, '-c', FIXTURES / 'closure_tls_bootstrap.cpp', '-o', bootstrap)
    paths = ('elf/d1-closure-tls-fixture.o', 'elf/rtld.os', *SUPPORT)
    if not all('shared/' + path in rtld['artifacts'] for path in paths):
        raise ValueError('rtld manifest is missing a closure TLS input')
    fixture, gnu_rtld, *support = (proof / 'shared' / name for name in paths)
    state = output / 'rtld-local-entry.o'
    run('localize_entry', 'objcopy', '--localize-symbol=_start', gnu_rtld, state)
    run('link_guest', 'ld', '--gc-sections', '-z', 'noexecstack', '-z', 'max-page-size=4096',
        '--build-id=none', '-Map', output / 'link.map', '-T', sysroot / 'user.ld',
        sysroot / 'usr/lib/xos_start.o', bootstrap, fixture, state, *support, '-o', elf)
    run('undefined', 'nm', '-u', elf)
    if (output / 'undefined.log').stat().st_size:
        raise ValueError('closure TLS probe has unresolved dependencies')
    report['program_headers'] = verify_elf(elf)
    report['guest_elf_sha256'] = sha(elf)
    return elf


def exercise(args, report, elf):
    with tempfile.TemporaryDirectory(prefix='xos_d1_closure_tls_') as folder:
        disk = Path(folder) / 'work.img'
        create_fat32(disk, 512)
        for path in ('/bin', '/tests'):
            transfer(disk, 'mkdir', path)
        transfer(disk, 'import', '/bin/closure_tls', elf)
        for name in report['dependencies']:
            transfer(disk, 'import', '/tests/' + name, args.output / name)
        guest = Guest(args.system / 'xos-install.iso', 'closure_tls', work_disk=disk,
                      qmp_enabled=False, log_dir=args.output)
        try:
            report['qemu_command'] = guest.command
            report['qemu_version'] = subprocess.check_output(
                [guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=90)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=90)
            command(guest, 'demo quiet', b'demo tasks')
            baseline = resources(guest)
            report.update(resources_before=baseline, runs={})
            for name, suffix, marker, code in (
                    ('exhausted', ' heap-limit', OOM, b'127'),
                    ('ordinary', '', SUCCESS, b'0')):
                result = command(guest, 'exec-file /bin/closure_tls' + suffix,
                                 b'kind=exited code=', timeout=60)
                after = resources(guest)
                report['runs'][name] = {'output': result.decode(errors='replace'), 'resources_after': after}
                if (marker not in result or after != baseline
                        or re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', result) != [code]):
                    raise AssertionError(name + ' GNU TLS run did not meet its gate: ' + repr(result))
        finally:
            guest.close()
            report['serial_sha256'] = sha(args.output / 'closure_tls_serial.log')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'sdk-build', 'profile', 'rtld-proof', 'output'):
        parser.add_argument('--' + name, type=lambda value: Path(value).resolve(), required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True)
    report = {'status': 'failed', 'scope': 'GNU initial rtld TLS with an authenticated DSO closure',
              'shared_interpreter_executed': False, 'commands': {}}
    try:
        system, sdk, rtld, artifacts = bind_rtld_inputs(args, report, FIXTURE, 'closure_tls_fixture_sha256')
        elf = build(args, report, rtld)
        exercise(args, report, elf)
        if (bind_system(args.system) != system or verify_profile(load_json(args.profile), 'glibc', args.sdk_build) != sdk
                or sha(args.rtld_proof / 'manifest.json') != report['rtld_manifest_sha256']
                or sha(elf) != report['guest_elf_sha256']
                or any(sha(path) != digest for path, digest in artifacts.items())
                or any(sha(args.output / name) != item['sha256'] for name, item in report['dependencies'].items())):
            raise ValueError('bound acceptance inputs changed during the guest run')
        report['status'] = 'passed_subset'
    finally:
        write_report(args.output / 'report.json', report)
    print(report['status'])


if __name__ == '__main__':
    main()
