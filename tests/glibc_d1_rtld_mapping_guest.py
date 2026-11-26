#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the real GNU rtld XOS mapping backend with authenticated native pins."""
import argparse
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from boot_smoke import Guest
from build_glibc_program import verify_elf
from build_glibc_sdk import inputs as sdk_inputs
from glibc_d1_layout_guest import BIASES, PHDR
from glibc_g1_probe import clean_build_environment, tool_identity
from make_work_disk import create_fat32
from process_smoke import command, resources
from shell_launch_support import bind_system, sha, write_report
from task_smoke import send_bytes
from work_disk import transfer
from xypm_format import load_json
from xypm_sdk_profile import GLIBC_STDIO_RECEIVER, require_stdio_marker, verify_profile

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/glibc_d1'
OVERLAY = ROOT / 'src/ports/glibc/sysdeps/xos'
PAGE = 4096


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
    ranges = []
    for _, flags, offset, vaddr, _, file_bytes, mem_bytes, align in loads:
        assert flags in (4, 5, 6) and offset + file_bytes <= len(data) and file_bytes <= mem_bytes
        assert align >= PAGE and vaddr % align == offset % align and bias % align == 0
        ranges.append((vaddr & -PAGE, (vaddr + mem_bytes + PAGE - 1) & -PAGE))
    assert {p[1] for p in loads} == {4, 5, 6}
    assert all(end <= start for (_, end), (start, _) in zip(ranges, ranges[1:]))
    hole = next(end for (_, end), (start, _) in zip(ranges, ranges[1:]) if end < start)
    pages = sum((end - start) // PAGE for start, end in ranges)
    assert (pages > 4096) == (label == 'large')
    digest = ','.join(hex(byte) for byte in bytes.fromhex(sha(path)))
    for field, value in {'bias': bias, 'bytes': len(data), 'span': ranges[-1][1],
                         'hole': hole, 'pages': pages}.items():
        header.write(f'static constexpr u64 {label}_{field} = {value};\n')
    header.write(f'static constexpr u8 {label}_digest[] = {{{digest}}};\n')
    return {'sha256': sha(path), 'pages': pages, 'bias': bias, 'entry': bias + entry}


def build(args, directory, report, rtld):
    sysroot = args.sdk_build / 'sysroot'
    lib = sysroot / 'usr/lib'
    sdk = args.system / 'sdk'
    manifest = load_json(args.sdk_build / 'manifest.json')
    tools = {name: tool_identity('x86_64-elf-' + name) for name in ('gcc', 'g++', 'as', 'ld', 'readelf')}
    for name, info in tools.items():
        assert info['sha256'] == manifest['tools']['x86_64-elf-' + name]['sha256']
    tool_dir = directory / 'tools'
    tool_dir.mkdir()
    for name in ('as', 'ld'):
        (tool_dir / name).symlink_to(tools[name]['path'])
    env, report['sanitized_environment'] = clean_build_environment(os.environ)
    env['LC_ALL'] = 'C'
    report['tools'], report['commands'] = tools, {}

    def run(name, argv):
        argv = list(map(str, argv))
        report['commands'][name] = argv
        log_file = directory / (name + '.log')
        with log_file.open('w') as log:
            subprocess.run(argv, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        return log_file.read_text()

    cflags = ['-B' + str(tool_dir) + '/', '--sysroot=' + str(sysroot), '-nostdinc', '-O2',
              '-mno-red-zone', '-fno-builtin', '-fno-stack-protector', '-Wall', '-Wextra', '-Werror',
              '-isystem', sysroot / 'usr/include', '-isystem', lib / 'compiler-include']
    report['dependencies'] = {}
    with (directory / 'dependency_plan.hpp').open('x') as header:
        for label, bias, words in zip(('small', 'large'), BIASES, (1024, 4194304)):
            obj, image = directory / (label + '.o'), directory / (label + '.so')
            run('compile_' + label, [tools['gcc']['path'], *cflags, '-fPIC', '-ffreestanding',
                                     '-DD1_BSS_WORDS=' + str(words), '-c',
                                     FIXTURES / 'rtld_dependency.c', '-o', obj])
            run('link_' + label, [tools['ld']['path'], '-shared', '-e', 'd1_dependency', '-soname',
                                  'lib' + label + '.so', '-z', 'noexecstack', '-z', 'max-page-size=8192',
                                  '-z', 'separate-code', '--build-id=none', '--no-undefined', '-o', image, obj])
            inspection = run('inspect_' + label, [tools['readelf']['path'], '-hW', '-lW', '-dW', '-rW', image])
            assert 'There are no relocations in this file.' in inspection
            report['dependencies'][label] = describe(image, label, bias, header)

    early, late, elf = (directory / name for name in ('early.o', 'late.o', 'probe.elf'))
    run('compile_early', [tools['g++']['path'], *cflags, '-fno-pie', '-ffreestanding', '-fno-exceptions',
                          '-fno-rtti', '-nostdinc++', '-std=gnu++20', '-I', sdk / 'include', '-I', OVERLAY,
                          '-I', directory, '-c', FIXTURES / 'rtld_mapping_guest.cpp', '-o', early])
    run('compile_late', [tools['gcc']['path'], *cflags, '-fno-pie', '-I', OVERLAY,
                         '-c', FIXTURES / 'rtld_mapping_late.c', '-o', late])
    run('link_guest', [tools['gcc']['path'], *cflags[:2], '-nostdlib', '-static', '-no-pie',
                       '-Wl,--build-id=none', '-Wl,-z,noexecstack', '-Wl,-z,max-page-size=4096',
                       '-Wl,--wrap=__xos_glibc_start', '-T', sysroot / 'user.ld', '-o', elf,
                       *(lib / name for name in ('xos_start.o', 'crti.o', 'crtbegin.o', 'xos_start_c.o')),
                       early, late, rtld / 'xos_rtld_mapping.os', rtld / 'xos_file_session.os',
                       sysroot / GLIBC_STDIO_RECEIVER, '-Wl,--start-group', lib / 'libc.a',
                       lib / 'libxos_terminal.a', sdk / 'lib/libxos.a', lib / 'libgcc.a',
                       '-Wl,--end-group', lib / 'crtend.o', lib / 'crtn.o'])
    report['program_headers'] = verify_elf(elf)
    require_stdio_marker(elf.read_bytes(), elf.name)
    report['guest_elf_sha256'] = sha(elf)
    return elf


def exercise(args, directory, elf, report):
    input_file = directory / 'input'
    input_file.write_bytes(b'ABCDEFGH\n')
    script = directory / 'probe.sh'
    script.write_text('/usr/bin/d1_rtld_map < /tests/input\nrc=$?\n'
                      'printf "D1_RTLD_MAP_RC=%s\\n" "$rc"\nexit "$rc"\n')
    with tempfile.TemporaryDirectory(prefix='xos_d1_rtld_mapping_') as folder:
        disk = Path(folder) / 'work.img'
        create_fat32(disk, 512)
        for path in ('/usr', '/usr/bin', '/tests'):
            transfer(disk, 'mkdir', path)
        for path, source in (('/usr/bin/dash', args.dash), ('/usr/bin/d1_rtld_map', elf),
                             ('/tests/small.so', directory / 'small.so'), ('/tests/large.so', directory / 'large.so'),
                             ('/tests/input', input_file), ('/tests/probe.sh', script)):
            transfer(disk, 'import', path, source)
        guest = Guest(args.system / 'xos-install.iso', 'rtld_mapping', work_disk=disk,
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
            output = command(guest, 'dash /tests/probe.sh', b'kind=exited code=', timeout=150)
            report['output'] = output.decode(errors='replace')
            for label, dependency in report['dependencies'].items():
                marker = f'D1_RTLD_{label.upper()} pages={dependency["pages"]} holes=reserved r_rx_rw=checked'
                assert marker.encode() in output, output
            match = re.search(rb'D1_RTLD_DEPENDENCY_MAPPED early=(\d+) late=(\d+) inherited=EFGH', output)
            assert match and int(match[2]) == int(match[1]) + 2, output
            assert b'D1_RTLD_MAP_RC=0' in output, output
            assert re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', output) == [b'0'], output
            report['resources_after'] = resources(guest)
            assert report['resources_after'] == report['resources_before']
        finally:
            guest.close()
            report['serial_sha256'] = sha(directory / 'rtld_mapping_serial.log')


def main():
    if not __debug__:
        raise SystemExit('the rtld mapping guest gate requires Python assertions')
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'sdk-build', 'profile', 'dash', 'dash-receipt', 'rtld-proof', 'output'):
        parser.add_argument('--' + name, type=lambda value: Path(value).resolve(), required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'scope': 'shared rtld mapping objects in a native static startup harness',
              'shared_interpreter_executed': False}
    try:
        system = bind_system(args.system)
        profile = load_json(args.profile)
        assert 'stdio_transfer' in profile['features']
        sdk = verify_profile(profile, 'glibc', args.sdk_build)
        preparation = args.rtld_proof / 'prepared/manifest.json'
        manifest_path = args.rtld_proof / 'manifest.json'
        rtld = load_json(manifest_path)
        assert rtld['status'] == 'rtld_entry_compiled_startup_blocked'
        assert sha(preparation) == rtld['preparation_manifest_sha256']
        sdk_manifest = args.sdk_build / 'manifest.json'
        assert sdk_inputs() == load_json(preparation)['inputs'] == load_json(sdk_manifest)['inputs']
        assert rtld['source_sha256'] == load_json(sdk_manifest)['source_sha256']
        assert sha(args.dash) == load_json(args.dash_receipt)['sha256']
        for relative, digest in rtld['artifacts'].items():
            assert sha(args.rtld_proof / relative) == digest
        report.update(build_id=system['build_id'], iso_sha256=sha(args.system / 'xos-install.iso'),
                      system_manifest_sha256=sha(args.system / 'manifest.json'), sdk_sha256=sha(sdk_manifest),
                      profile_sha256=sha(args.profile), rtld_manifest_sha256=sha(manifest_path),
                      rtld_objects=rtld['artifacts'], dash_sha256=sha(args.dash),
                      dash_receipt_sha256=sha(args.dash_receipt))
        elf = build(args, args.output, report, args.rtld_proof / 'shared/elf')
        exercise(args, args.output, elf, report)
        assert bind_system(args.system) == system
        assert verify_profile(load_json(args.profile), 'glibc', args.sdk_build) == sdk
        assert all(sha(args.rtld_proof / path) == digest for path, digest in rtld['artifacts'].items())
        assert sha(elf) == report['guest_elf_sha256']
        report['status'] = 'passed_subset'
    finally:
        write_report(args.output / 'report.json', report)
    print(report['status'])


if __name__ == '__main__':
    main()
