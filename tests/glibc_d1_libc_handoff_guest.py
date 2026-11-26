#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the actual shared GNU G3 file component with native inherited FDs."""
import argparse
from io import StringIO
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from boot_smoke import Guest
from build_glibc_program import verify_elf
from build_glibc_sdk import inputs as sdk_inputs
from glibc_d1_closure_tls_guest import FIXTURES, OVERLAY, RELOCATION_SUPPORT, ROOT, SUPPORT
from glibc_d1_interpreter_entry_guest import describe
from glibc_g1_probe import clean_build_environment, tool_identity
from glibc_static_guest import build_newlib_parent
from make_work_disk import create_fat32
from probe_glibc_rtld import LIBC_HANDOFF_COMPONENT_OBJECTS
from process_smoke import command, resources
from shell_launch_support import bind_system, sha, write_report
from task_smoke import send_bytes
from work_disk import transfer
from xypm_sdk_profile import GLIBC_STDIO_RECEIVER, require_stdio_marker, verify_profile

COMPONENT_SUPPORT = ('src/ports/glibc/terminal_support.cpp', 'src/user/sdk/terminal_client.cpp',
                     'src/user/arch/x86_64/syscall.cpp')
GNU_SUPPORT = (*SUPPORT[:-2], *RELOCATION_SUPPORT, 'elf/xos_rtld_libc_handoff.os',
               'elf/dl-lookup-direct.os', 'elf/dl-version.os', 'string/rtld-strncmp.os',
               'elf/d1-libc-handoff-fixture.o')
CASES = {
    'spawn': b'D1_LIBC_HANDOFF_OK native=v2 inherited=EFGH sequence=continuous',
    'exec': b'D1_LIBC_HANDOFF_OK native=v3 inherited=EFGH alias=shared cloexec=closed sequence=continuous',
    'version': b'D1_LIBC_HANDOFF_REFUSED version=checked files=early',
}


def build(args, report, rtld):
    output, proof = args.output, args.rtld_proof / 'shared'
    sysroot = args.sdk_build / 'sysroot'
    lib = sysroot / 'usr/lib'
    tools = {name: tool_identity('x86_64-elf-' + name)
             for name in ('gcc', 'g++', 'as', 'ld', 'nm', 'readelf', 'objcopy')}
    for name, tool in tools.items():
        assert tool['sha256'] == rtld['tools']['x86_64-elf-' + name]['sha256'], name
    report['tools'] = tools
    env, report['sanitized_environment'] = clean_build_environment(os.environ)
    env['LC_ALL'] = 'C'
    tool_dir = output / 'tools'
    tool_dir.mkdir()
    for name in ('as', 'ld'):
        (tool_dir / name).symlink_to(tools[name]['path'])

    def run(stage, tool, *arguments):
        argv = [tools[tool]['path'], *map(str, arguments)]
        report['commands'][stage] = argv
        log_path = output / (stage + '.log')
        with log_path.open('w') as log:
            subprocess.run(argv, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        return log_path.read_text()

    cxx_flags = ['-B' + str(tool_dir) + '/', '--sysroot=' + str(sysroot),
                 '-nostdinc', '-nostdinc++', '-std=gnu++20', '-O2', '-mno-red-zone',
                 '-ffreestanding', '-fno-builtin', '-fno-exceptions', '-fno-rtti',
                 '-fno-stack-protector', '-Wall', '-Wextra', '-Werror',
                 '-isystem', sysroot / 'usr/include', '-isystem', lib / 'compiler-include',
                 '-I', ROOT / 'src/shared/include', '-idirafter', ROOT / 'src/user/include']
    support = []
    for relative in COMPONENT_SUPPORT:
        source = ROOT / relative
        obj = output / (source.stem + '.os')
        run('compile_' + source.stem, 'g++', *cxx_flags, '-fPIC', '-fvisibility=hidden',
            '-ffunction-sections', '-fdata-sections', '-fno-use-cxa-atexit', '-fno-threadsafe-statics',
            '-c', source, '-o', obj)
        support.append(obj)

    version_map = (proof / 'libc.map').read_text()
    symbol = '__xos_file_adopt_startup;'
    assert version_map.count(symbol) == 1
    required = (*LIBC_HANDOFF_COMPONENT_OBJECTS, 'libc.map', 'elf/rtld.os', *GNU_SUPPORT)
    assert {'shared/' + path for path in required} <= rtld['artifacts'].keys()
    report['components'] = {}
    images = []
    with (output / 'closure_tls_plan.hpp').open('x') as plan:
        for role, file_name in (('private', 'libg3.so'), ('wrong', 'libg3-old.so')):
            script = output / (role + '.map')
            replacement = 'd1_handoff_sequence; __errno_location;'
            if role == 'private':
                replacement += ' ' + symbol
            script.write_text(version_map.replace(symbol, replacement) + (
                '\nD1_OLD { global: ' + symbol + ' };\n' if role == 'wrong' else ''))
            image = output / file_name
            run('link_' + role, 'ld', '-shared', '-e', 'read', '-soname', 'libg3.so', '--version-script', script,
                '--gc-sections', '-z', 'defs', '-z', 'relro', '-z', 'now', '-z', 'noexecstack',
                '-z', 'max-page-size=8192', '-z', 'common-page-size=4096', '-z', 'separate-code',
                '--build-id=none', '-Bsymbolic-functions', '-o', image,
                *(proof / path for path in LIBC_HANDOFF_COMPONENT_OBJECTS), *support)
            info = run('inspect_' + role, 'readelf', '-hW', '-lW', '-dW', '-rW', '--dyn-syms', image)
            version = 'GLIBC_PRIVATE' if role == 'private' else 'D1_OLD'
            assert '__xos_file_adopt_startup@@' + version in info and 'd1_handoff_sequence@@GLIBC_PRIVATE' in info
            assert '__errno_location@@GLIBC_PRIVATE' in info
            assert all(name + '@@GLIBC_2.44' in info for name in ('read', 'close'))
            assert all(tag not in info for tag in ('(NEEDED)', '(TEXTREL)', '(RPATH)', '(RUNPATH)'))
            relocs = set(re.findall(r'R_X86_64_\w+', info))
            assert 'R_X86_64_TPOFF64' in relocs and relocs <= {'R_X86_64_TPOFF64', 'R_X86_64_RELATIVE'}
            bias = 0x140040000000
            image_info = describe(image, role, bias, StringIO())
            image_info.update(version=version, relocations=sorted(relocs))
            report['components'][role] = image_info
            octets = ','.join(hex(octet) for octet in bytes.fromhex(image_info['sha256']))
            plan.write(f'static constexpr u8 {role}_digest[] = {{{octets}}};\n')
            images.append(image)
        plan.write('static constexpr dependency dependencies[] = {\n')
        for role, image in zip(('private', 'wrong'), images):
            plan.write(f'    {{"/tests/{image.name}", "libg3.so", 0x140040000000ULL, '
                       f'{image.stat().st_size}, {report["components"][role]["span"]}, {role}_digest}},\n')
        plan.write('};\n')

    early, state, elf = (output / name for name in ('early.o', 'rtld-local-entry.o', 'd1_libc_handoff.elf'))
    run('compile_bootstrap', 'g++', *cxx_flags, '-fno-pie', '-DD1_LIBC_HANDOFF',
        '-I', OVERLAY, '-I', output,
        '-c', FIXTURES / 'closure_tls_bootstrap.cpp', '-o', early)
    run('localize_entry', 'objcopy', '--localize-symbol=_start', proof / 'elf/rtld.os', state)
    run('link_guest', 'ld', '--gc-sections', '-z', 'noexecstack', '-z', 'max-page-size=4096',
        '--build-id=none', '-Map', output / 'link.map', '-T', sysroot / 'user.ld', '-o', elf,
        lib / 'xos_start.o', sysroot / GLIBC_STDIO_RECEIVER, early, state,
        *(proof / path for path in GNU_SUPPORT))
    assert not run('undefined_guest', 'nm', '-u', elf).strip()
    require_stdio_marker(elf.read_bytes(), elf.name)
    report['program_headers'] = verify_elf(elf)
    report['guest_elf_sha256'] = sha(elf)
    parent = build_newlib_parent(args.system, output, report,
                                'glibc_d1/libc_handoff_exec.c', 'd1_libc_exec')
    return elf, parent, images


def exercise(args, report, inputs):
    output = args.output
    elf, parent, images = inputs
    (output / 'input').write_bytes(b'ABCDEFGH')
    (output / 'cleanup').write_bytes(b'close on exec')
    (output / 'spawn.sh').write_text('/usr/bin/d1_libc_handoff ordinary < /tests/input\n')
    (output / 'version.sh').write_text('/usr/bin/d1_libc_handoff wrong-version < /tests/input\n'
                                      'rc=$?\ntrue >> /tests/libg3-old.so || exit 71\n'
                                      'printf "D1_LIBC_REFUSAL_PIN=reopened\\n"\nexit "$rc"\n')
    with tempfile.TemporaryDirectory(prefix='xos_d1_libc_handoff_') as temporary:
        disk = Path(temporary) / 'work.img'
        create_fat32(disk, 512)
        for folder in ('/usr', '/usr/bin', '/tests'):
            transfer(disk, 'mkdir', folder)
        for destination, source in (('/usr/bin/dash', args.dash), ('/usr/bin/d1_libc_handoff', elf),
                                    ('/usr/bin/d1_libc_exec', parent),
                                    *((f'/tests/{item}', output / item) for item in
                                      ('input', 'cleanup', 'spawn.sh', 'version.sh')),
                                    *((f'/tests/{image.name}', image) for image in images)):
            transfer(disk, 'import', destination, source)
        guest = Guest(args.system / 'xos-install.iso', 'libc_handoff', work_disk=disk,
                      qmp_enabled=False, log_dir=output)
        try:
            report['qemu_command'] = guest.command
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'],
                                                             text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=40)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=40)
            command(guest, 'demo quiet', b'demo tasks')
            report['resources_before'] = resources(guest)
            for name, invocation in (('spawn', 'dash /tests/spawn.sh'), ('exec', 'd1_libc_exec'),
                                     ('version', 'dash /tests/version.sh')):
                serial = command(guest, invocation, b'kind=exited code=', timeout=120)
                after = resources(guest)
                report['runs'][name] = {'output': serial.decode(errors='replace'), 'resources_after': after}
                assert CASES[name] in serial and after == report['resources_before'], serial
                assert re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', serial) == [b'0'], serial
                if name == 'version':
                    assert b'D1_LIBC_REFUSAL_PIN=reopened' in serial, serial
        finally:
            guest.close()
            report['serial_sha256'] = sha(output / 'libc_handoff_serial.log')


def main():
    if not __debug__:
        raise SystemExit('run this acceptance test without Python optimization so its checks execute')
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'sdk-build', 'profile', 'dash', 'dash-receipt', 'rtld-proof', 'output'):
        parser.add_argument('--' + name, type=lambda value: Path(value).resolve(), required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'scope': 'versioned GNU shared G3 file component and native FD handoff',
              'shared_interpreter_executed': False, 'gnu_dl_main_executed': False,
              'commands': {}, 'elfs': {}, 'runs': {}}
    try:
        system = bind_system(args.system)
        profile = json.loads(args.profile.read_bytes())
        assert 'stdio_transfer' in profile['features']
        sdk = verify_profile(profile, 'glibc', args.sdk_build)
        rtld_path = args.rtld_proof / 'manifest.json'
        rtld = json.loads(rtld_path.read_bytes())
        prepared = args.rtld_proof / 'prepared/manifest.json'
        assert rtld['status'] == 'rtld_entry_compiled_startup_blocked'
        assert rtld['preparation_manifest_sha256'] == sha(prepared)
        assert json.loads(prepared.read_bytes())['inputs'] == sdk_inputs()
        assert rtld['source_sha256'] == json.loads((args.sdk_build / 'manifest.json').read_bytes())['source_sha256']
        assert rtld['libc_handoff_fixture_sha256'] == sha(FIXTURES / 'libc_handoff_runtime.c')
        assert rtld['libc_handoff_sequence_sha256'] == sha(FIXTURES / 'libc_handoff_sequence.c')
        for name, digest in rtld['artifacts'].items():
            assert sha(args.rtld_proof / name) == digest, name
        assert sha(args.dash) == json.loads(args.dash_receipt.read_bytes())['sha256']
        report.update(system_build_id=system['build_id'], system_manifest_sha256=sha(args.system / 'manifest.json'),
                      iso_sha256=sha(args.system / 'xos-install.iso'), sdk_sha256=sha(args.sdk_build / 'manifest.json'),
                      profile_sha256=sha(args.profile), rtld_manifest_sha256=sha(rtld_path),
                      dash_sha256=sha(args.dash), dash_receipt_sha256=sha(args.dash_receipt))
        inputs = build(args, report, rtld)
        exercise(args, report, inputs)
        assert bind_system(args.system) == system
        assert verify_profile(json.loads(args.profile.read_bytes()), 'glibc', args.sdk_build) == sdk
        assert sha(rtld_path) == report['rtld_manifest_sha256'] and sha(args.dash) == report['dash_sha256']
        assert sha(inputs[0]) == report['guest_elf_sha256']
        assert sha(inputs[1]) == report['elfs']['d1_libc_exec']['elf_sha256']
        for info, image in zip(report['components'].values(), inputs[2]):
            assert sha(image) == info['sha256']
        report['status'] = 'passed_subset'
    finally:
        write_report(args.output / 'report.json', report)
    print(report['status'])


if __name__ == '__main__':
    main()
