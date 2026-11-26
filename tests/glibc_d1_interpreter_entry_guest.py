#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prepare a native interpreter entry from pinned linked ELF files in QEMU."""
import argparse
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import time

from boot_smoke import Guest
from build_glibc_program import verify_elf
from build_glibc_sdk import inputs as sdk_inputs
from glibc_d1_layout_guest import BIASES, PHDR
from glibc_g1_probe import clean_build_environment, tool_identity
from make_work_disk import create_fat32
from probe_glibc_rtld import SYSDEP_INVOCATION_ELF, SYSDEP_INVOCATION_LEAVES
from process_smoke import command, resources
from shell_launch_support import bind_system, sha, write_report
from task_smoke import send_bytes
from work_disk import transfer
from xypm_format import load_json
from xypm_sdk_profile import GLIBC_STDIO_RECEIVER, require_stdio_marker, verify_profile

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/glibc_d1'
OVERLAY = ROOT / 'src/ports/glibc/sysdeps/xos'
INTERPRETER = b'/usr/lib/xos/glibc_dynamic_v1/ld_xos_x86_64.so.1\0'
NATIVE_SUPPORT = ('elf/rtld.os', 'elf/xos_rtld_sysdep_start.os', 'elf/xos_rtld_mapping.os',
                  'elf/xos_file_session.os', 'elf/xos_rtld_heap.os',
                  'posix/rtld-environ.os', 'string/rtld-strcmp.os')
INVOCATION_SUPPORT = ('elf/xos_rtld_sysdep_invoke.os', 'elf/dl-minimal-malloc.os', 'elf/dl-mutex.os',
                      *(f'elf/{name}' for name in SYSDEP_INVOCATION_ELF),
                      *(f'{subdir}/rtld-{name}.os' for subdir, names in SYSDEP_INVOCATION_LEAVES
                        for name in names))
INVOCATION_RUNS = {
    'ordinary': (b'0', b'D1_SYSDEP_INVOKE_OK callback=1 cpu=gnu entry=mapped file=continuous heap=live'),
    'secure': (b'127', b'XOS rtld: secure descriptor startup is unavailable'),
    'obsolete': (b'127', b'XOS rtld: invalid native startup handoff'),
}


def describe(path, label, bias, header):
    data = path.read_bytes()
    assert data[:7] == b'\x7fELF\x02\x01\x01'
    assert struct.unpack_from('<HHI', data, 16) == (3, 62, 1)
    entry, phoff = struct.unpack_from('<QQ', data, 24)
    size, count = struct.unpack_from('<HH', data, 54)
    assert size == PHDR.size and 0 < count <= 64 and phoff + count * size <= len(data)
    table = [PHDR.unpack_from(data, phoff + i * size) for i in range(count)]
    loads = [p for p in table if p[0] == 1 and p[6] != 0]
    assert loads and loads[0][2:4] == (0, 0)
    for _, flags, offset, vaddr, _, file_bytes, mem_bytes, align in loads:
        assert flags in (4, 5, 6) and offset + file_bytes <= len(data) and file_bytes <= mem_bytes
        assert align >= 4096 and vaddr % align == offset % align and bias % align == 0
    span = max((p[3] + p[6] + 4095) & ~4095 for p in loads)
    header.write(f'static constexpr u32 {label}_bytes = {len(data)};\n')
    digest = ','.join(hex(byte) for byte in bytes.fromhex(sha(path)))
    header.write(f'static constexpr u8 {label}_digest[] = {{{digest}}};\n')
    header.write(f'static constexpr u64 {label}_span = {span};\n')
    header.write(f'static constexpr elf::segment {label}_loads[] = {{\n')
    for _, flags, offset, vaddr, _, file_bytes, mem_bytes, _ in loads:
        header.write(f'    {{{offset}, {vaddr}, {file_bytes}, {mem_bytes}, {flags}}},\n')
    header.write('};\n')
    header.write(f'static constexpr mapped_image {label}_image = '
                 f'{{{bias}, {entry}, {label}_loads, {len(loads)}}};\n')
    if label == 'main':
        ph, = (p for p in table if p[0] == 6)
        interp, = (p for p in table if p[0] == 3)
        assert ph[2] == phoff and ph[5] == count * size
        assert data[interp[2]:interp[2] + interp[5]] == INTERPRETER
        header.write(f'static constexpr main_headers main_phdr = {{{phoff}, {ph[3]}, {count}}};\n')
    return {'entry': bias + entry, 'phnum': count, 'sha256': sha(path), 'span': span}


def build(args, directory, report, rtld, sysroot):
    lib = sysroot / 'usr/lib'
    sdk = args.system / 'sdk'
    manifest = load_json(args.sdk_build / 'manifest.json')
    assert manifest['inputs'] == sdk_inputs()
    names = ('gcc', 'g++', 'as', 'ld', 'readelf', 'objcopy') if args.native_sysdep else (
        'gcc', 'g++', 'as', 'ld', 'readelf')
    compiler = {tool: tool_identity('x86_64-elf-' + tool) for tool in names}
    for name, info in compiler.items():
        assert info['sha256'] == manifest['tools']['x86_64-elf-' + name]['sha256']
    tools = directory / 'tools'
    tools.mkdir()
    for name in ('as', 'ld'):
        (tools / name).symlink_to(compiler[name]['path'])
    env, removed = clean_build_environment(os.environ)
    env['LC_ALL'] = 'C'
    report['tools'], report['sanitized_environment'] = compiler, removed
    report['commands'] = {}

    def run(name, argv):
        argv = list(map(str, argv))
        report['commands'][name] = argv
        with (directory / (name + '.log')).open('w') as log:
            subprocess.run(argv, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)

    cflags = ['-B' + str(tools) + '/', '--sysroot=' + str(sysroot), '-nostdinc', '-O2',
              '-mno-red-zone', '-fno-builtin', '-fno-stack-protector', '-Wall', '-Wextra', '-Werror',
              '-isystem', sysroot / 'usr/include', '-isystem', lib / 'compiler-include']
    pic, pie, image, dependency = (directory / name for name in
                                  ('image.o', 'main.pie', 'interpreter.so', 'dependency.so'))
    run('compile_images', [compiler['gcc']['path'], *cflags, '-fPIC', '-ffreestanding',
                           '-c', FIXTURES / 'layout_dso.c', '-o', pic])
    ld = [compiler['ld']['path'], '-e', 'd1_entry', '-z', 'noexecstack', '-z', 'max-page-size=8192',
          '-z', 'separate-code', '--build-id=none', '--no-undefined']
    run('link_pie', [*ld, '-pie', '--dynamic-linker', INTERPRETER[:-1].decode(), '-o', pie, pic])
    run('link_shared_input', [*ld, '-shared', '-o', image, pic])
    run('link_dependency', [*ld, '-shared', '-soname', 'libhandoff.so', '-o', dependency, pic])
    run('elf_inputs', [compiler['readelf']['path'], '-hW', '-lW', '-dW', pie, image, dependency])
    with (directory / 'interpreter_plan.hpp').open('x') as header:
        report['images'] = {name: describe(path, name, bias, header) for name, path, bias in (
            ('main', pie, BIASES[0]), ('interpreter', image, BIASES[1]),
            ('dependency', dependency, 0x140020000000))}

    early, late, elf = (directory / name for name in ('entry.o', 'late.o', 'entry.elf'))
    bootstrap = 'sysdep_start_bootstrap.cpp' if args.native_sysdep else 'interpreter_entry_guest.cpp'
    fixture_flags = ['-DD1_SYSDEP_INVOKE'] if args.sysdep_invocation else []
    run('compile_bootstrap', [compiler['g++']['path'], *cflags, '-fno-pie', '-ffreestanding',
                              '-fno-exceptions', '-fno-rtti', '-nostdinc++', '-std=gnu++20',
                              '-I', sdk / 'include', '-I', ROOT / 'src/user/loader/glibc_d1',
                              '-I', OVERLAY, '-I', directory, *fixture_flags,
                              '-c', FIXTURES / bootstrap, '-o', early])
    if args.native_sysdep:
        rtld_state = directory / 'rtld-local-entry.o'
        run('localize_entry', [compiler['objcopy']['path'], '--localize-symbol=_start',
                               rtld.parent / 'rtld.os', rtld_state])
        run('link_guest', [compiler['ld']['path'], '--gc-sections', '-z', 'noexecstack',
                           '-z', 'max-page-size=4096', '--build-id=none', '-Map', directory / 'link.map',
                           '-T', sysroot / 'user.ld',
                           '-o', elf, lib / 'xos_start.o', early, rtld_state, rtld,
                           *(rtld.parent.parent / path for path in args.native_support if path != 'elf/rtld.os'),
                           '--start-group', sdk / 'lib/libxos_loader.a', sdk / 'lib/libxos.a',
                           lib / 'libgcc.a', '--end-group'])
        report['program_headers'] = verify_elf(elf)
        report['guest_elf_sha256'] = sha(elf)
        return pie, image, dependency, elf
    run('compile_late', [compiler['gcc']['path'], *cflags, '-fno-pie', '-I', OVERLAY,
                         '-c', FIXTURES / 'interpreter_entry_late.c', '-o', late])
    run('link_guest', [compiler['gcc']['path'], *cflags[:2], '-nostdlib', '-static', '-no-pie',
                       '-Wl,--build-id=none', '-Wl,-z,noexecstack', '-Wl,-z,max-page-size=4096',
                       '-Wl,--gc-sections', '-Wl,--wrap=__xos_glibc_start', '-T', sysroot / 'user.ld', '-o', elf,
                       *(lib / item for item in ('xos_start.o', 'crti.o', 'crtbegin.o', 'xos_start_c.o')),
                       early, late, rtld, rtld.parent / 'xos_rtld_mapping.os',
                       rtld.parent / 'xos_file_session.os', rtld.parent / 'xos_rtld_heap.os',
                       rtld.parent / 'dl-minimal-malloc.os', sysroot / GLIBC_STDIO_RECEIVER, '-Wl,--start-group',
                       sdk / 'lib/libxos_loader.a', lib / 'libc.a', lib / 'libxos_terminal.a',
                       sdk / 'lib/libxos.a', lib / 'libgcc.a', '-Wl,--end-group',
                       lib / 'crtend.o', lib / 'crtn.o'])
    report['program_headers'] = verify_elf(elf)
    require_stdio_marker(elf.read_bytes(), elf.name)
    report['guest_elf_sha256'] = sha(elf)
    return pie, image, dependency, elf


def exercise(args, directory, inputs, report):
    data = directory / 'input'
    data.write_bytes(b'ABCDEFGH\n')
    if args.native_sysdep:
        scripts = {mode: directory / (mode + '.sh') for mode in args.native_runs}
        environment = 'D1_ENTRY_ENV=verified'
        if args.sysdep_invocation:
            environment += ' MALLOC_PERTURB_=73 GLIBC_TUNABLES_OTHER=ordinary'
        for mode, script in scripts.items():
            launch = f'{environment} /usr/bin/d1_entry {mode}\n'
            if args.sysdep_invocation:
                launch += 'rc=$?\nprintf "D1_SYSDEP_CHILD_RC=%s\\n" "$rc"\n'
                if mode != 'obsolete':
                    launch += ('true >> /tests/dependency.so || exit 71\n'
                               'printf "D1_SYSDEP_WRITER=reopened\\n"\n')
                launch += 'exit "$rc"\n'
            script.write_text(launch)
        if args.sysdep_invocation:
            scripts['check_writer'] = directory / 'check_writer.sh'
            scripts['check_writer'].write_text('true >> /tests/dependency.so\n')
    else:
        script = directory / 'child.sh'
        script.write_text('/usr/bin/d1_entry < /tests/input\nrc=$?\n'
                          'printf "D1_INTERPRETER_ENTRY_RC=%s\\n" "$rc"\nexit "$rc"\n')
        empty = directory / 'empty.sh'
        empty.write_text(script.read_text().replace('/usr/bin/d1_entry <', '/usr/bin/d1_entry empty <', 1))
        scripts = {'child': script, 'empty': empty}
    pie, image, dependency, elf = inputs
    with tempfile.TemporaryDirectory(prefix='xos_d1_interpreter_entry_') as folder:
        disk = Path(folder) / 'work.img'
        create_fat32(disk, 512)
        for path in ('/usr', '/usr/bin', '/tests'):
            transfer(disk, 'mkdir', path)
        for path, source in (('/usr/bin/dash', args.dash), ('/usr/bin/d1_entry', elf),
                             ('/tests/main.pie', pie), ('/tests/interpreter.so', image), ('/tests/dependency.so', dependency),
                             ('/tests/input', data),
                             *((f'/tests/{mode}.sh', script) for mode, script in scripts.items())):
            transfer(disk, 'import', path, source)
        guest = Guest(args.system / 'xos-install.iso', 'interpreter_entry', work_disk=disk,
                      qmp_enabled=False, log_dir=directory)
        try:
            report['qemu_command'] = guest.command
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'],
                                                             text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=40)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=40)
            command(guest, 'demo quiet', b'demo tasks')
            report['resources_before'] = resources(guest)
            if args.native_sysdep:
                report['runs'] = {}
                for mode, (code, marker) in args.native_runs.items():
                    result = command(guest, f'dash /tests/{mode}.sh', b'kind=exited code=', timeout=120)
                    after = resources(guest)
                    report['runs'][mode] = {'output': result.decode(errors='replace'),
                                            'resources_after': after}
                    assert marker in result and after == report['resources_before'], result
                    assert re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', result) == [code], result
                    if args.sysdep_invocation:
                        assert b'D1_SYSDEP_OBSERVER_FAIL' not in result and b'D1_NATIVE_SYSDEP_FAIL' not in result
                        assert result.count(INVOCATION_RUNS['ordinary'][1]) == (code == b'0'), result
                        assert b'D1_SYSDEP_CHILD_RC=' + code + b'\n' in result, result
                        if mode != 'obsolete':
                            assert b'D1_SYSDEP_WRITER=reopened' in result, result
                if args.sysdep_invocation:
                    # The rejected obsolete record never became an authenticated
                    # owner. Let the files service observe native process death.
                    deadline = time.monotonic() + 10
                    attempts = report['obsolete_writer_recovery'] = []
                    while True:
                        remaining = deadline - time.monotonic()
                        assert remaining > 0, attempts
                        result = command(guest, 'dash /tests/check_writer.sh', b'kind=exited code=',
                                         timeout=remaining)
                        attempts.append(result.decode(errors='replace'))
                        if re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', result) == [b'0']:
                            break
                        assert b'Device or resource busy' in result, result
                    assert resources(guest) == report['resources_before']
                return
            result = command(guest, 'dash /tests/child.sh', b'kind=exited code=', timeout=120)
            report['output'] = result.decode(errors='replace')
            assert re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', result) == [b'0'], result
            assert b'D1_INTERPRETER_STACK low=rejected below_min=rejected' in result, result
            assert b'D1_RTLD_HEAP_PLAN_REQUIRED prepare=checked attach=checked' in result, result
            assert b'D1_RTLD_EARLY_HEAP_OK batches=2 rollback=clean rw_nx=checked' in result, result
            assert b'D1_RTLD_ENTRY_CLOSURE_OK soname=libhandoff.so' in result, result
            assert b'D1_INTERPRETER_ENTRY_RC=0' in result, result
            match = re.search(rb'D1_INTERPRETER_ENTRY_PREPARED phdr=(\d+) interpreter=0x([0-9a-f]+)'
                              rb' early=(\d+) late=(\d+) inherited=EFGH early_heap=live', result)
            assert match, result
            phnum, entry, early, late = match.groups()
            assert int(phnum) == report['images']['main']['phnum']
            assert int(entry, 16) == report['images']['interpreter']['entry']
            assert int(late) == int(early) + 2
            assert resources(guest) == report['resources_before']
            result = command(guest, 'dash /tests/empty.sh', b'kind=exited code=', timeout=120)
            report['empty_output'] = result.decode(errors='replace')
            assert re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', result) == [b'0'], result
            assert b'D1_RTLD_HEAP_PLAN_REQUIRED prepare=checked attach=checked' in result, result
            assert b'D1_RTLD_EARLY_HEAP_OK batches=2 rollback=clean rw_nx=checked' in result, result
            assert b'D1_RTLD_ENTRY_EMPTY_OK no_requests' in result, result
            assert b'D1_INTERPRETER_ENTRY_RC=0' in result, result
            assert b'inherited=EFGH' in result, result
            report['resources_after'] = resources(guest)
            assert report['resources_after'] == report['resources_before']
        finally:
            guest.close()
            report['serial_sha256'] = sha(directory / 'interpreter_entry_serial.log')


def main():
    if not __debug__:
        raise SystemExit('run this acceptance test without Python optimization so its checks execute')
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('system', 'sdk-build', 'profile', 'dash', 'dash-receipt', 'rtld-proof', 'output'):
        parser.add_argument('--' + field, type=lambda value: Path(value).resolve(), required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--native-sysdep', action='store_true',
                       help='exercise actual GNU startup globals and the authenticated native session')
    modes.add_argument('--sysdep-invocation', action='store_true',
                       help='exercise _dl_sysdep_start with a GNU-signature observer and real runtime support')
    args = parser.parse_args()
    args.native_sysdep |= args.sysdep_invocation
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'scope': 'native preparation and shared rtld entry checker',
              'shared_interpreter_executed': False}
    if args.native_sysdep:
        report['scope'] = 'native preparation into the GNU rtld OS startup state'
        prefix = 'sysdep_invocation' if args.sysdep_invocation else 'native_sysdep'
        args.native_support = (*NATIVE_SUPPORT, 'elf/d1-' + prefix.replace('_', '-') + '-fixture.o')
        args.native_runs = {mode: (b'0', f'D1_NATIVE_SYSDEP_OK secure={secure} argv_env=gnu auxv=gnu '
                                  'file=continuous heap=live'.encode())
                            for mode, secure in (('ordinary', 0), ('secure', 1))}
        if args.sysdep_invocation:
            args.native_support += INVOCATION_SUPPORT
            args.native_runs = INVOCATION_RUNS
            report.update(scope='native GNU OS callback boundary with a typed observer', gnu_dl_main_executed=False)
    try:
        system = bind_system(args.system)
        profile = load_json(args.profile)
        assert 'stdio_transfer' in profile['features']
        sdk = verify_profile(profile, 'glibc', args.sdk_build)
        rtld_manifest = load_json(args.rtld_proof / 'manifest.json')
        rtld = args.rtld_proof / 'shared/elf/xos_rtld_entry.os'
        assert rtld_manifest['status'] == 'rtld_entry_compiled_startup_blocked'
        for source, digest in rtld_manifest['artifacts'].items():
            assert sha(args.rtld_proof / source) == digest
        if args.native_sysdep:
            assert rtld_manifest[prefix + '_fixture_sha256'] == sha(FIXTURES / 'sysdep_start_state.c')
            assert {'shared/' + path for path in args.native_support} <= rtld_manifest['artifacts'].keys()
        assert rtld_manifest['source_sha256'] == load_json(args.sdk_build / 'manifest.json')['source_sha256']
        preparation = args.rtld_proof / 'prepared/manifest.json'
        assert sha(preparation) == rtld_manifest['preparation_manifest_sha256']
        assert load_json(preparation)['inputs'] == sdk_inputs()
        assert sha(args.dash) == load_json(args.dash_receipt)['sha256']
        report.update(build_id=system['build_id'], iso_sha256=sha(args.system / 'xos-install.iso'),
                      sdk_sha256=sha(args.sdk_build / 'manifest.json'), profile_sha256=sha(args.profile),
                      system_manifest_sha256=sha(args.system / 'manifest.json'),
                      rtld_object_sha256=sha(rtld), rtld_manifest_sha256=sha(args.rtld_proof / 'manifest.json'),
                      dash_sha256=sha(args.dash), dash_receipt_sha256=sha(args.dash_receipt))
        inputs = build(args, args.output, report, rtld, args.sdk_build / 'sysroot')
        exercise(args, args.output, inputs, report)
        assert bind_system(args.system) == system
        assert verify_profile(load_json(args.profile), 'glibc', args.sdk_build) == sdk
        assert sha(rtld) == report['rtld_object_sha256'] and sha(args.dash) == report['dash_sha256']
        assert sha(inputs[0]) == report['images']['main']['sha256']
        assert sha(inputs[1]) == report['images']['interpreter']['sha256']
        assert sha(inputs[2]) == report['images']['dependency']['sha256']
        assert sha(inputs[3]) == report['guest_elf_sha256']
        report['status'] = 'passed_subset'
    finally:
        write_report(args.output / 'report.json', report)
    print(report['status'])


if __name__ == '__main__':
    main()
