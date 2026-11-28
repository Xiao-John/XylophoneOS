#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise native identity admission and volatile generation state on host and XOS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_smoke import Guest
from build_glibc_program import verify_elf
from glibc_g1_probe import clean_build_environment, tool_identity
from make_work_disk import create_fat32
from process_smoke import command, resources
from shell_launch_support import bind_system, check_result, sha, write_report
from task_smoke import send_bytes
from toolchain import COMMON_FLAGS, X86_FLAGS
from work_disk import transfer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    system, output = args.system.resolve(strict=True), args.output.resolve()
    system_binding = bind_system(system)
    output.mkdir(parents=True, exist_ok=False)
    env, removed = clean_build_environment(os.environ)
    env['LC_ALL'] = 'C'
    tools = {name: tool_identity(name) for name in ('g++', 'x86_64-elf-g++', 'x86_64-elf-gcc',
                                                   'x86_64-elf-ld', 'x86_64-elf-readelf')}
    if any(not item.get('available') for item in tools.values()):
        raise ValueError('host and target compiler tools are required')
    source_names = ('src/user/loader/dynamic/identity.cpp', 'src/user/loader/dynamic/generation.cpp',
                    'tests/fixtures/dynamic_admission/cases.cpp', 'tests/fixtures/dynamic_admission/guest.cpp')
    inputs = {name: sha(ROOT / name) for name in source_names}
    inputs['tests/dynamic_admission_guest.py'] = sha(Path(__file__))
    include = output / 'include'
    for root in ('src/shared/include/xos', 'src/user/include/xos'):
        for path in sorted((ROOT / root).rglob('*')):
            if path.is_file():
                destination = include / 'xos' / path.relative_to(ROOT / root)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists() and destination.read_bytes() != path.read_bytes():
                    raise ValueError('conflicting native SDK header')
                shutil.copyfile(path, destination)
                inputs[str(path.relative_to(ROOT))] = sha(path)
    inputs['src/user/loader/image_reader.hpp'] = sha(ROOT / 'src/user/loader/image_reader.hpp')
    report = {'status': 'failed', 'scope': 'identity and generation admission components',
              'public_dynamic_launch': 'not_implemented_by_this_component',
              'build_id': system_binding['build_id'], 'system_manifest_sha256': sha(system / 'manifest.json'),
              'system_iso_sha256': sha(system / 'xos-install.iso'), 'tools': tools,
              'inputs': inputs, 'sanitized_environment': removed, 'commands': {}}

    def run(label, argv):
        command = list(map(str, argv))
        report['commands'][label] = command
        with (output / (label + '.log')).open('w') as log:
            subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)

    try:
        abi = hashlib.sha256(json.dumps({'compiler': tools['x86_64-elf-gcc']['sha256'],
            'header': inputs['src/shared/include/xos/dynamic_abi.hpp']}, sort_keys=True).encode()).digest()
        identity = struct.pack('<Q10IQ32s40s', 0x31594e44534f5858, 1, 128, 4, 62, 1, 1, 1, 1, 2, 1,
                               1, abi, bytes(40))
        assembly = output / 'identity.S'
        assembly.write_text('.section .note.xos,"a",@note\n.balign 4\n.long 4,128,0x584f5301\n'
            '.asciz "XOS"\n.byte ' + ','.join(str(byte) for byte in identity)
            + '\n.text\n.globl identity_fixture\nidentity_fixture:\nmov $23,%eax\nret\n'
            + '.section .note.GNU-stack,"",@progbits\n')
        run('compile_identity', [tools['x86_64-elf-gcc']['path'], '-c', assembly, '-o', output / 'identity.o'])
        dso = output / 'identity.so'
        run('link_identity', [tools['x86_64-elf-ld']['path'], '-shared', '-e', 'identity_fixture',
            '-soname', 'libidentity.so', '-z', 'now', '-z', 'relro', '-z', 'noexecstack',
            '-z', 'max-page-size=8192', '-z', 'separate-code', '--build-id=none',
            output / 'identity.o', '-o', dso])
        run('inspect_identity', [tools['x86_64-elf-readelf']['path'], '-hW', '-lW', '-nW', '-dW', dso])
        data = dso.read_bytes()
        phoff = struct.unpack_from('<Q', data, 32)[0]
        count = struct.unpack_from('<H', data, 56)[0]
        programs = [(phoff + i * 56, struct.unpack_from('<IIQQQQQQ', data, phoff + i * 56)) for i in range(count)]
        note_header, note = next(item for item in programs if item[1][0] == 4)
        stack_header = next(offset for offset, item in programs if item[0] == 0x6474e551)
        identity_offset = note[2] + 16
        assert data[identity_offset:identity_offset + 128] == identity
        load_header = next(offset for offset, item in programs if item[0] == 1
                           and item[2] <= identity_offset and identity_offset + 128 <= item[2] + item[5])
        vector = lambda value: '{' + ','.join(str(byte) for byte in value) + '}'
        (output / 'fixture.hpp').write_text('#pragma once\n#include <xos/dynamic.hpp>\n'
            + 'static constexpr xos::u8 fixture_bytes[] = ' + vector(data) + ';\n'
            + 'static constexpr xos::dynamic::object_identity fixture_identity = '
            + '{xos::dynamic::identity_magic,1,128,xos::dynamic::object_role::library,62,1,1,1,1,2,1,1,'
            + vector(abi) + ',{}};\n'
            + 'static constexpr xos::dynamic::generation_object fixture_object = {' + str(len(data)) + ','
            + vector(hashlib.sha256(data).digest()) + ',fixture_identity,0,0,0,{},"","",{}};\n'
            + ''.join('static constexpr xos::u64 ' + name + ' = ' + str(value) + ';\n' for name, value in (
                ('fixture_identity_offset', identity_offset), ('fixture_note_header', note_header),
                ('fixture_stack_header', stack_header), ('fixture_identity_load_header', load_header))))
        host_main = output / 'host.cpp'
        host_main.write_text('#include <cstdio>\nextern "C" void run_admission_cases();\n'
            'static unsigned checks,failures;\n'
            'extern "C" void admission_check(const char* name,bool ok){++checks;if(!ok)++failures;'
            'std::printf("D3_ADMISSION_%s %s\\n",ok?"PASS":"FAIL",name);}\n'
            'int main(){run_admission_cases();std::printf("checks=%u failures=%u\\n",checks,failures);return failures?1:0;}\n')
        native = [ROOT / name for name in source_names[:3]]
        run('host_compile', [tools['g++']['path'], '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror',
            '-Wconversion', '-Wshadow', '-I', include, '-I', output, *native, host_main, '-o', output / 'host'])
        run('host_cases', [output / 'host'])
        report['host_checks'] = (output / 'host_cases.log').read_text().count('D3_ADMISSION_PASS ')
        objects = []
        # Guest consumes the public native loader archive from the bound SDK.
        # Only its test cases and entry are linked as additional objects.
        for index, path in enumerate((ROOT / source_names[2], ROOT / source_names[3])):
            obj = output / (str(index) + '.o')
            run('target_compile_' + str(index), [tools['x86_64-elf-g++']['path'], *COMMON_FLAGS, *X86_FLAGS,
                '-I', include, '-I', output, '-I', ROOT / 'src/user/loader', '-c', path, '-o', obj])
            objects.append(obj)
        binary = output / 'admission.elf'
        sdk = system / 'sdk'
        run('target_link', [tools['x86_64-elf-ld']['path'], '-z', 'noexecstack', '-z', 'max-page-size=4096',
            '--build-id=none', '--no-undefined', '-T', sdk / 'user.ld', sdk / 'crt0.o', *objects,
            '--start-group', sdk / 'lib/libxos_loader.a', sdk / 'lib/libxos.a', '--end-group', '-o', binary])
        verify_elf(binary)
        with tempfile.TemporaryDirectory(prefix='dynamic_admission_') as directory:
            disk = Path(directory) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/identity.so', dso)
            transfer(disk, 'import', '/bin/admission', binary)
            guest = Guest(system / 'xos-install.iso', 'dynamic_admission', work_disk=disk,
                          qmp_enabled=False, log_dir=output)
            try:
                report['qemu_command'] = guest.command
                report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
                guest.expect(b'xos64> ', timeout=40)
                send_bytes(guest, b'run\r')
                guest.expect_supervisor(trace=True, timeout=40)
                command(guest, 'demo quiet', b'demo tasks')
                report['resources_before'] = resources(guest)
                result = command(guest, 'exec-file /bin/admission', b'kind=', timeout=90)
                report['guest_output'] = result.decode(errors='replace')
                report['guest_checks'] = result.count(b'D3_ADMISSION_PASS ')
                check_result(result, 0, ((f'D3_ADMISSION_OK checks={report["host_checks"] + 1}').encode(),
                                        b'D3_ADMISSION_PASS same_native_file_pin_and_cursor'))
                if report['guest_checks'] != report['host_checks'] + 1 or b'D3_ADMISSION_FAIL' in result:
                    raise ValueError('guest case inventory differs')
                report['resources_after'] = resources(guest)
                if report['resources_after'] != report['resources_before']:
                    raise ValueError('guest resource baseline changed')
            finally:
                guest.close()
        if bind_system(system) != system_binding or any(sha(ROOT / name) != digest for name, digest in inputs.items()):
            raise ValueError('system or source changed during validation')
        if any(sha(Path(tool['path'])) != tool['sha256'] for tool in tools.values()):
            raise ValueError('validation tool changed')
        report['artifacts'] = {path.name: sha(path) for path in (assembly, dso, output / 'fixture.hpp', binary)}
        report['status'] = 'passed_subset'
    finally:
        write_report(output / 'report.json', report)
    print(report['status'])


if __name__ == '__main__':
    main()
