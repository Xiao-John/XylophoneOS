#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Execute exactly one build-produced PIC fixture in two native high-address layouts."""
import argparse
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

from boot_smoke import Guest
from glibc_static_guest import system_sources
from process_smoke import command, resources
from task_smoke import pump, send_bytes

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_glibc_sdk import inputs as glibc_inputs
from glibc_g1_probe import clean_build_environment, tool_identity
from make_work_disk import create_fat32
from work_disk import transfer
from xypm_format import load_json, require, sha_file
from xypm_sdk_profile import metadata_snapshot, verify_profile

FIXTURES = ROOT / 'tests/fixtures/glibc_d1'
PAGE = 4096
BIASES = (0x100000200000, 0x180040000000)
PT_LOAD, PT_DYNAMIC, PT_GNU_STACK, PT_GNU_RELRO = 1, 2, 0x6474e551, 0x6474e552
PHDR = struct.Struct('<IIQQQQQQ')
DYN = struct.Struct('<qQ')
RELA = struct.Struct('<QQq')


def fixture_layout(data):
    """Recognize this test's linked shape and extract its single relocation."""
    require(64 <= len(data) <= 65536 and data[:7] == b'\x7fELF\x02\x01\x01', 'invalid fixture ELF')
    require(struct.unpack_from('<HHI', data, 16) == (3, 62, 1), 'fixture is not x86-64 ET_DYN')
    entry, phoff = struct.unpack_from('<QQ', data, 24)
    size, count = struct.unpack_from('<HH', data, 54)
    require(phoff == 64 and size == PHDR.size and count == 7 and phoff + count * size <= len(data),
            'fixture program header shape changed')
    headers = [PHDR.unpack_from(data, phoff + i * size) for i in range(count)]
    require([item[0] for item in headers] == [PT_LOAD] * 4 + [PT_DYNAMIC, PT_GNU_STACK, PT_GNU_RELRO],
            'unexpected fixture segment')
    loads = []
    page_end = 0
    hole = None
    for _, flags, offset, vaddr, _, filesz, memsz, align in headers[:4]:
        require(align == 2 * PAGE and offset % align == vaddr % align and offset + filesz <= len(data)
                and filesz <= memsz and vaddr + memsz <= 65536, 'invalid fixture segment bounds')
        if memsz == 0:
            require(flags == 4, 'unexpected empty LOAD permission')
            continue
        start = vaddr // PAGE * PAGE
        end = (vaddr + memsz + PAGE - 1) // PAGE * PAGE
        require(start >= page_end, 'fixture LOAD pages overlap')
        if start > page_end and hole is None:
            hole = page_end
        page_end = end
        loads.append((offset, vaddr, filesz, memsz, start, end - start, flags))
    require([load[-1] for load in loads] == [4, 5, 6] and loads[0][1] == 0 and hole is not None,
            'expected distinct R/RX/RW loads and a gap')
    read, code, write = loads
    require(code[1] <= entry < code[1] + code[2] and write[3] - write[2] > PAGE,
            'fixture lacks a file-backed code entry or multi-page BSS')

    _, _, relro_file, relro, _, relro_filesz, relro_size, _ = headers[-1]
    relro_start, relro_end = relro // PAGE * PAGE, relro + relro_size
    require(headers[-2][1] == 6 and headers[-1][1] == 4 and relro_start == write[4]
            and relro == write[1] and relro_file == write[0] and relro_size == relro_filesz
            and relro_end % PAGE == 0 and relro_end < write[1] + write[2],
            'fixture RELRO does not leave a separate initialized writable page')
    _, flags, offset, vaddr, _, filesz, memsz, _ = headers[4]
    require(flags == 6 and relro <= vaddr < vaddr + memsz <= relro_end and memsz == filesz
            and offset == relro_file + vaddr - relro and filesz % DYN.size == 0,
            'fixture DYNAMIC table is outside RELRO')
    entries = list(DYN.iter_unpack(data[offset:offset + filesz]))
    declared = {}
    tag_set = {5, 6, 7, 8, 9, 10, 11, 24, 0x6ffffef5, 0x6ffffff9, 0x6ffffffb}
    for tag, value in entries:
        if tag == 0:
            break
        require(tag in tag_set and tag not in declared, 'unexpected fixture dynamic tag')
        declared[tag] = value
    require((0, 0) in entries and set(declared) == tag_set and declared[8] == declared[9] == RELA.size
            and declared[0x6ffffff9] == 1, 'fixture does not have exactly one RELA entry')
    rela = declared[7]
    require(read[1] <= rela <= read[1] + read[2] - RELA.size, 'RELA table not in file-backed R segment')
    site, info, addend = RELA.unpack_from(data, read[0] + rela - read[1])
    require(info == 8 and site % 8 == addend % 8 == 0 and relro <= site <= relro_end - 8
            and relro_end <= addend <= write[1] + write[2] - 8,
            'expected one symbol-free R_X86_64_RELATIVE from RELRO to initialized writable data')
    return {'image_span': page_end, 'entry_offset': entry, 'relocation_site': site,
            'relocated_data': addend, 'relro_start': relro_start, 'relro_size': relro_end - relro_start,
            'hole_offset': hole, 'loads': loads}


def embed(data, layout, header):
    protection = {4: 'PROT_READ', 5: 'PROT_READ | PROT_EXEC', 6: 'PROT_READ | PROT_WRITE'}
    with header.open('x') as stream:
        stream.write('static const unsigned char image[] = {\n')
        for offset in range(0, len(data), 16):
            stream.write('    ' + ', '.join(f'0x{byte:02x}' for byte in data[offset:offset + 16]) + ',\n')
        stream.write('};\nstatic const struct load_segment loads[] = {\n')
        for *values, flags in layout['loads']:
            stream.write('    {' + ', '.join([*(hex(value) for value in values), protection[flags]]) + '},\n')
        stream.write('};\n')
        for name, value in layout.items():
            if name != 'loads':
                stream.write(f'static const size_t {name} = {value:#x};\n')


def build_fixture(args, output, report):
    sdk = args.sdk_build / 'sysroot'
    profile = load_json(args.profile)
    binding = verify_profile(profile, 'glibc', args.sdk_build)
    manifest, manifest_hash = metadata_snapshot(args.sdk_build / 'manifest.json',
                                               profile['sdk_binding']['sdk_manifest_sha256'])
    require(glibc_inputs() == manifest['inputs'], 'XOS glibc SDK source snapshot differs')
    tools = {}
    for suffix in ('gcc', 'as', 'ld', 'readelf'):
        name = 'x86_64-elf-' + suffix
        identity = tool_identity(name)
        require(identity['available'] and identity['sha256'] == manifest['tools'][name]['sha256'],
                name + ' differs from the SDK build')
        tools[suffix] = identity
    env, _ = clean_build_environment(os.environ)
    env['LC_ALL'] = 'C'
    tool_dir = output / 'tools'
    tool_dir.mkdir()
    (tool_dir / 'as').symlink_to(tools['as']['path'])
    obj, dso, harness = (output / name for name in ('layout.o', 'layout.so', 'harness.elf'))
    compile_dso = [tools['gcc']['path'], '-B' + str(tool_dir) + '/', '--sysroot=' + str(sdk), '-nostdinc',
                   '-isystem', str(sdk / 'usr/include'), '-isystem', str(sdk / 'usr/lib/compiler-include'),
                   '-D__XOS__', '-std=gnu11', '-O2', '-ffreestanding', '-fPIC', '-mcmodel=small', '-mno-red-zone',
                   '-fno-stack-protector', '-fno-asynchronous-unwind-tables', '-fno-unwind-tables', '-fvisibility=hidden',
                   '-c', str(FIXTURES / 'layout_dso.c'), '-o', str(obj)]
    link_dso = [tools['ld']['path'], '-shared', '-e', 'd1_entry', '-z', 'relro', '-z', 'now', '-z', 'noexecstack',
                '-z', 'max-page-size=8192', '-z', 'separate-code', '--build-id=none', '--no-undefined', '--hash-style=gnu',
                '-o', str(dso), str(obj)]
    inspect_dso = [tools['readelf']['path'], '-hW', '-lW', '-rW', '-dW', str(dso)]
    build_harness = [sys.executable, str(ROOT / 'scripts/build_glibc_program.py'), '--sdk', str(sdk),
                     '--profile', str(args.profile), '--source', str(FIXTURES / 'layout_guest.c'),
                     '--include-dir', str(output), '--output', str(harness)]
    steps = report['commands'] = {}

    def run(name, argv):
        steps[name] = argv
        with (output / (name + '.log')).open('w') as log:
            subprocess.run(argv, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)

    run('compile_dso', compile_dso)
    run('link_dso', link_dso)
    run('readelf', inspect_dso)
    data = dso.read_bytes()
    layout = fixture_layout(data)
    header = output / 'layout_fixture.h'
    embed(data, layout, header)
    run('build_harness', build_harness)
    require(harness.read_bytes().count(data) == 1, 'the guest does not embed the exact linked ELF exactly once')
    require(verify_profile(load_json(args.profile), 'glibc', args.sdk_build) == binding,
            'SDK binding changed during fixture generation')
    report.update(profile_binding=binding, sdk_manifest_sha256=manifest_hash, tools=tools, layout=layout,
                  artifacts={path.name: sha_file(path) for path in (obj, dso, header, harness)})
    return harness, layout


def exercise(image, harness, layout, output, report):
    with tempfile.TemporaryDirectory(prefix='d1_layout_') as temporary:
        disk = Path(temporary) / 'test.img'
        create_fat32(disk, 512)
        transfer(disk, 'mkdir', '/bin')
        transfer(disk, 'import', '/bin/d1_layout', harness)
        guest = Guest(image, 'd1_layout', work_disk=disk, iso=True, qmp_enabled=False, log_dir=output)
        try:
            report['qemu_command'] = guest.command
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=30)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=30)
            pump(guest, 1)
            before = resources(guest)
            observed = command(guest, 'exec-file /bin/d1_layout', b'kind=', timeout=45)
            cases = re.findall(rb'D1_LAYOUT ([0-9a-f]+) ([0-9a-f]+) ([0-9a-f]+) ([0-9a-f]+)', observed)
            actual = [tuple(int(value, 16) for value in row) for row in cases]
            expected = [(bias, bias + layout['relocated_data'], 0x448f, 0x4c8d) for bias in BIASES]
            require(actual == expected and b'D1_LAYOUT_PASS collision=EEXIST bss=zero relro=read-only reuse=ok' in observed
                    and b'kind=exited code=0' in observed, 'two-layout execution failed')
            require(resources(guest) == before, 'resources changed after successful execution')
            report['layouts'] = actual
            report['resource_baseline'] = before
            report['faults'] = {}
            for mode, offset in (('relro-write', 'relocation_site'), ('rw-exec', 'relocated_data'), ('hole-read', 'hole_offset')):
                observed = command(guest, 'exec-file /bin/d1_layout ' + mode, b'kind=', timeout=45)
                address = BIASES[0] + layout[offset]
                marker = f'D1_EXPECT_FAULT {mode} {address:x}'.encode()
                fault = re.search(rb'event=fault pid=(\d+) vector=14 rip=(0x[0-9a-f]+) cr2=(0x[0-9a-f]+)', observed)
                wait = re.search(rb'\[wait\] pid=(\d+) kind=faulted code=0\b', observed)
                require(marker in observed and fault and wait and fault[1] == wait[1] and int(fault[3], 16) == address,
                        f'{mode}: expected page fault at {address:#x}, got {observed[-1000:]!r}')
                require((int(fault[2], 16) == address) == (mode == 'rw-exec'), 'unexpected faulting instruction address')
                require(resources(guest) == before, f'{mode}: resources changed after reaping')
                report['faults'][mode] = {'vector': 14, 'address': address, 'rip': int(fault[2], 16)}
        finally:
            guest.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'sdk-build', 'profile', 'output'):
        parser.add_argument('--' + name, required=True, type=lambda value: Path(value).resolve())
    args = parser.parse_args()
    args.output.mkdir(parents=True)
    image, manifest = args.system / 'xos-install.iso', args.system / 'manifest.json'
    report = {'status': 'failed', 'scope': 'D1-C fixed fixture only'}
    try:
        system = load_json(manifest)
        initial_manifest = sha_file(manifest)
        require(system_sources() == system['sources'], 'system source snapshot differs')
        image_hash = sha_file(image)
        require(image_hash == system['artifacts'][image.name]['sha256'], 'system ISO differs')
        report.update(system_build_id=system['build_id'], system_manifest_sha256=initial_manifest,
                      iso_sha256=image_hash, runner_sha256=sha_file(Path(__file__)))
        harness, layout = build_fixture(args, args.output, report)
        exercise(image, harness, layout, args.output, report)
        sdk_manifest, _ = metadata_snapshot(args.sdk_build / 'manifest.json', report['sdk_manifest_sha256'])
        require(sha_file(manifest) == initial_manifest and sha_file(image) == image_hash
                and system_sources() == system['sources'] and glibc_inputs() == sdk_manifest['inputs']
                and verify_profile(load_json(args.profile), 'glibc', args.sdk_build) == report['profile_binding']
                and all(sha_file(args.output / name) == checksum for name, checksum in report['artifacts'].items()),
                'qualification inputs changed during guest replay')
        report['status'] = 'passed_subset'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS D1 high-address fixture, RELRO, NX, holes and native collision')


if __name__ == '__main__':
    main()
