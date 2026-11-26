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
           'setjmp/rtld-__longjmp.os', 'csu/errno-loc.os', 'csu/errno.os')
RELOCATION_SUPPORT = ('elf/dl-reloc.os', 'elf/dl-lookup.os', 'elf/dl-setup_hash.os',
                      'elf/dl-audit.os', 'elf/dl-misc.os', 'elf/dl-scope.os', 'elf/tlsdesc.os',
                      'elf/dl-tlsdesc.os', 'elf/dl-trampoline.os', 'elf/dl-runtime.os',
                      'elf/dl-get-cpu-features.os', 'elf/dl-thread_gscope_wait.os', 'elf/dl-profile.os',
                      'misc/rtld-mprotect.os', 'csu/rtld-errno.os', 'string/rtld-stpcpy.os',
                      'string/rtld-strcmp.os', 'string/rtld-memcmp.os',
                      'nptl/rtld-lowlevellock.os', 'nptl/rtld-xos_lll_futex.os', 'nptl/rtld-xos_wait_word.os')
SUCCESS = (b'D1_CLOSURE_TLS_OK modules=3 dsos=2 tdata=checked tbss=zero '
           b'dtv=1 tp=preserved libc_errno=checked')
RELOCATION_OK = b'D1_GNU_RELOC_OK dsos=2 tpoff64=gnu relro=sealed errno=dynamic tp=preserved'
OOM = b'XOS rtld: cannot allocate initial TLS slotinfo'


def describe(path, index, alignment, value, plan, inspection, relocate):
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
    template = struct.pack('<Q', value) if relocate else bytes((value, 0x3c, 0x19))
    bss = 8 if relocate else 129
    if (flags != 4 or filesz < len(template) or memsz - filesz < bss or align != alignment
            or data[offset:offset + len(template)] != template
            or not any(p[1] & 4 and p[2] <= offset <= offset + filesz <= p[2] + p[5]
                       and p[3] + offset - p[2] == address for p in loads)):
        raise ValueError('PT_TLS does not describe the expected file-backed template')
    span = (max(p[3] + p[6] for p in loads) + PAGE - 1) & -PAGE
    digest = sha(path)
    octets = ','.join(hex(octet) for octet in bytes.fromhex(digest))
    plan.write(f'static constexpr u8 digest_{index}[] = {{{octets}}};\n')
    result = {'sha256': digest, 'bias': BIASES[index], 'bytes': len(data), 'span': span,
              'tls_file_offset': offset, 'tls_vaddr': address, 'tls_file_bytes': filesz,
              'tls_memory_bytes': memsz, 'tls_alignment': align}
    if relocate:
        relro, = [header for header in table if header[0] == 0x6474e552]
        begin, end = relro[3] & -PAGE, (relro[3] + relro[6]) & -PAGE
        relocs = re.findall(r'^([0-9a-f]+)\s+[0-9a-f]+\s+(R_X86_64_\w+)(.*)$',
                            inspection, re.MULTILINE)
        needed = re.findall(r'\(NEEDED\).*Shared library: \[([^\]]+)\]', inspection)
        if (needed != (['libie_base.so'] if index else []) or not relocs
                or any(kind != 'R_X86_64_TPOFF64' or not begin <= int(place, 16) <= end - 8
                       for place, kind, _ in relocs)
                or (index and not any('provider_tls' in symbol for _, _, symbol in relocs))):
            raise ValueError('linked DSO does not bind the planned TPOFF64/RELRO closure')
        result.update(needed=needed, relocations=[(int(place, 16), kind, symbol.strip())
                                                for place, kind, symbol in relocs],
                      relro_pages=[begin, end])
    return result


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
        return (output / (stage + '.log')).read_text()

    flags = ['-B' + str(tool_dir) + '/', '--sysroot=' + str(sysroot), '-nostdinc',
             '-isystem', sysroot / 'usr/include', '-isystem', sysroot / 'usr/lib/compiler-include',
             '-O2', '-mno-red-zone', '-ffreestanding', '-fno-builtin',
             '-fno-stack-protector', '-Wall', '-Wextra', '-Werror']
    dependencies = report['dependencies'] = {}
    gnu = args.gnu_relocation
    names = ('libie_base.so', 'libie_use.so') if gnu else ('libtls1.so', 'libtls2.so')
    source = FIXTURES / ('relocation_dependency.c' if gnu else 'closure_tls_dependency.c')
    with (output / 'closure_tls_plan.hpp').open('x') as plan:
        for index, (name, alignment, value) in enumerate(zip(names, (64, 256), (0x51, 0xa7))):
            obj, dso = output / (name + '.o'), output / name
            dso_flags = [f'-DD1_TLS_ALIGNMENT={alignment}', f'-DD1_TLS_VALUE={value}']
            links = []
            if gnu:
                dso_flags = ['-ftls-model=initial-exec'] + (['-DD1_TLS_PROVIDER'] if index == 0 else [])
                links = ([proof / 'shared/csu/errno-loc.os', proof / 'shared/csu/errno.os']
                         if index == 0 else [output / names[0]])
            run('compile_' + name, 'gcc', *flags, '-fPIC', *dso_flags,
                '-c', source, '-o', obj)
            protection = ['-z', 'relro', '-z', 'now', '-z', 'common-page-size=4096',
                          '-Bsymbolic-functions'] if gnu else []
            run('link_' + name, 'ld', '-shared', '-e', 'd1_dependency', '-soname', name,
                '-z', 'max-page-size=8192', '-z', 'separate-code', '-z', 'noexecstack',
                '--no-undefined', '--build-id=none', *protection, '-o', dso, obj, *links)
            inspection = run('inspect_' + name, 'readelf', '-hW', '-lW', '-dW', '-rW', dso)
            dependencies[name] = describe(dso, index, alignment, value, plan, inspection, gnu)
        plan.write('static constexpr dependency dependencies[] = {\n')
        for index, (name, info) in enumerate(dependencies.items()):
            plan.write(f'    {{"/tests/{name}", "{name}", {info["bias"]}, {info["bytes"]}, '
                       f'{info["span"]}, digest_{index}}},\n')
        plan.write('};\n')

    bootstrap, elf = output / 'bootstrap.o', output / 'closure_tls.elf'
    run('compile_bootstrap', 'g++', *flags, '-fno-pie', '-fno-exceptions', '-fno-rtti',
        '-nostdinc++', '-std=gnu++20', '-I', args.system / 'sdk/include',
        '-I', OVERLAY, '-I', output, '-c', FIXTURES / 'closure_tls_bootstrap.cpp', '-o', bootstrap)
    fixture_name = 'elf/d1-gnu-relocation-fixture.o' if gnu else 'elf/d1-closure-tls-fixture.o'
    support_paths = SUPPORT[:-2] + RELOCATION_SUPPORT if gnu else SUPPORT
    paths = (fixture_name, 'elf/rtld.os', *support_paths)
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
            cases = (('ordinary', '', RELOCATION_OK, b'0'), ('repeated', '', RELOCATION_OK, b'0'))
            if not args.gnu_relocation:
                cases = (('exhausted', ' heap-limit', OOM, b'127'), ('ordinary', '', SUCCESS, b'0'))
            for name, suffix, marker, code in cases:
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
    parser.add_argument('--gnu-relocation', action='store_true',
                        help='exercise GNU initial-exec relocation and native RELRO on a linked DSO pair')
    args = parser.parse_args()
    args.output.mkdir(parents=True)
    report = {'status': 'failed', 'scope': 'GNU initial rtld TLS with an authenticated DSO closure',
              'shared_interpreter_executed': False,
              'shared_libc_leaf_scope': 'link-time resolved errno', 'commands': {}}
    if args.gnu_relocation:
        report.update(scope='GNU TPOFF64 relocation with an authenticated linked DSO pair',
                      shared_libc_leaf_scope='runtime relocated errno in the provider DSO')
    fixture, key = ((FIXTURES / 'relocation_runtime.c', 'gnu_relocation_fixture_sha256')
                    if args.gnu_relocation else (FIXTURE, 'closure_tls_fixture_sha256'))
    try:
        system, sdk, rtld, artifacts = bind_rtld_inputs(args, report, fixture, key)
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
