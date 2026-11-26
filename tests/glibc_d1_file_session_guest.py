#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise a native files session across the genuine static XOS glibc entry."""
import argparse
from pathlib import Path
import os
import re
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
from shell_launch_support import bind_system, sha, write_report
from task_smoke import send_bytes
from work_disk import transfer
from xypm_format import load_json
from xypm_sdk_profile import GLIBC_STDIO_RECEIVER, require_stdio_marker, verify_profile

FIXTURES = ROOT / 'tests/fixtures/glibc_d1'
OVERLAY = ROOT / 'src/ports/glibc/sysdeps/xos'


def build_fixture(sdk_build, profile, out, report):
    binding = verify_profile(profile, 'glibc', sdk_build)
    if 'stdio_transfer' not in profile['features']:
        raise ValueError('fixture requires a profile with the glibc stdio receiver')
    manifest = load_json(sdk_build / 'manifest.json')
    tools = {name: tool_identity('x86_64-elf-' + name)
             for name in ('gcc', 'as', 'ld', 'nm', 'readelf')}
    for name in ('gcc', 'as', 'ld'):
        if tools[name]['sha256'] != manifest['tools']['x86_64-elf-' + name]['sha256']:
            raise ValueError('compiler driver or assembler/linker differs from SDK')
    report['tools'] = tools
    env, report['sanitized_environment'] = clean_build_environment(os.environ)
    env['LC_ALL'] = 'C'
    tools_dir = out / 'link-tools'
    tools_dir.mkdir()
    for name in ('as', 'ld'):
        (tools_dir / name).symlink_to(tools[name]['path'])
    sdk = sdk_build / 'sysroot'
    lib = sdk / 'usr/lib'
    driver = [tools['gcc']['path'], '--sysroot=' + str(sdk), '-B' + str(tools_dir) + '/']
    flags = ['-std=gnu11', '-O2', '-g', '-mno-red-zone', '-fno-pie', '-fno-builtin',
             '-nostdinc', '-isystem', sdk / 'usr/include', '-isystem', lib / 'compiler-include',
             '-I', OVERLAY, '-Wall', '-Wextra', '-Werror']
    early_flags = ['-ffreestanding', '-fno-stack-protector']
    early, late, transport, elf = [out / name for name in
                                   ('early.o', 'late.o', 'transport.o', 'd1_file_session.elf')]
    files = [FIXTURES / 'file_session_early.c', FIXTURES / 'file_session_late.c',
             OVERLAY / 'xos_file_session.c', OVERLAY / 'xos_file_session.h',
             OVERLAY / 'xos_file_trap.h', OVERLAY / 'xos_file_wire.h',
             OVERLAY / 'xos_file_runtime.h', Path(__file__).resolve()]
    report['source_sha256'] = {str(path.relative_to(ROOT)): sha(path) for path in files}
    report['commands'] = {}

    def run(name, arguments):
        argv = list(map(str, arguments))
        report['commands'][name] = argv
        path = out / (name + '.log')
        with path.open('w') as log:
            subprocess.run(argv, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        return path.read_text()

    run('compile_early', [*driver, *flags, *early_flags, '-c', files[0], '-o', early])
    run('compile_late', [*driver, *flags, '-ftls-model=local-exec', '-c', files[1], '-o', late])
    run('compile_transport', [*driver, *flags, *early_flags, '-fPIC', '-c', files[2], '-o', transport])
    for name, obj, expected in (
            ('early', early, {'__xos_file_session_call', '__xos_file_adopt_early_session',
                              '__real___xos_glibc_start'}),
            ('transport', transport, set())):
        symbols = run(name + '_undefined', [tools['nm']['path'], '-u', obj])
        assert {line.split()[-1] for line in symbols.splitlines()} == expected
        # The compiler may emit a GOTPCREL relocation to the same unit's hidden symbols.
        relocs = run(name + '_relocations', [tools['readelf']['path'], '-rW', obj])
        assert not re.search(r'R_X86_64_(?:TLS|DTP|TPOFF|GOTTPOFF)', relocs)
    rest = ['libxos_terminal.a', 'libgcc.a']
    if (lib / 'libgcc_eh.a').is_file():
        rest += ['libgcc_eh.a']
    run('link', [*driver, '-static', '-no-pie', '-nostdlib', '-Wl,--build-id=none',
                 '-Wl,-z,noexecstack', '-Wl,-z,max-page-size=4096',
                 '-Wl,--wrap=__xos_glibc_start', '-T', sdk / 'user.ld', '-o', elf,
                 *(lib / name for name in ('xos_start.o', 'crti.o', 'crtbegin.o', 'xos_start_c.o')),
                 early, late, sdk / GLIBC_STDIO_RECEIVER, '-Wl,--start-group', lib / 'libc.a',
                 lib / 'libm.a', *(lib / name for name in rest), '-Wl,--end-group',
                 lib / 'crtend.o', lib / 'crtn.o'])
    report['program_headers'] = verify_elf(elf)
    require_stdio_marker(elf.read_bytes(), elf.name)
    report['elf_sha256'] = sha(elf)
    return elf, binding


def guest_case(system, dash, elf, out, report, death):
    name = 'service_exit' if death else 'healthy'
    directory = out / name
    directory.mkdir()
    data = directory / 'redirected_input'
    data.write_bytes(b'ABCDEFGH\n')
    script = directory / 'child.sh'
    mode = ' death' if death else ''
    script.write_text(f'/usr/bin/d1_file{mode} < /tests/input\nrc=$?\n'
                      'printf "D1_FILE_CHILD_RC=%s\\n" "$rc"\nexit "$rc"\n')
    with tempfile.TemporaryDirectory(prefix='xos_d1_file_session_') as folder:
        disk = Path(folder) / 'work.img'
        create_fat32(disk, 512)
        for path in ('/usr', '/usr/bin', '/tests'):
            transfer(disk, 'mkdir', path)
        for destination, source in (('/usr/bin/dash', dash), ('/usr/bin/d1_file', elf),
                                    ('/tests/input', data), ('/tests/child.sh', script)):
            transfer(disk, 'import', destination, source)
        guest = Guest(system / 'xos-install.iso', name, work_disk=disk,
                      qmp_enabled=False, log_dir=directory)
        try:
            report['qemu_command'] = guest.command
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'],
                                                             text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=40)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=40)
            command(guest, 'demo quiet', b'demo tasks')
            before = report['resources_before'] = resources(guest)
            if death:
                listing = command(guest, 'ps', b'name=files ')
                pids = re.findall(rb'^pid=(\d+) name=files ', listing, re.MULTILINE)
                assert len(pids) == 1
            result = command(guest, 'dash /tests/child.sh', b'kind=exited code=', timeout=95)
            report['output'] = result.decode(errors='replace')
            assert re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', result) == [b'0'], result
            marker = (rb'D1_FILE_DEATH early=4 error=-(?:5|110) late=EIO' if death else
                      rb'D1_FILE_HANDOFF early=3 late=5 inherited=EFGH')
            assert re.search(marker + rb'.*D1_FILE_CHILD_RC=0', result, re.DOTALL), result
            expected = before
            if death:
                reclaimed = rb'\[task\] event=reclaimed pid=' + pids[0] + rb' pages=(\d+)'
                freed = re.findall(reclaimed, result)
                assert len(freed) == 1 and re.search(reclaimed + rb'.*' + marker, result, re.DOTALL), result
                expected = (before[0] + int(freed[0]), before[1] - 1, before[2])
                assert b'name=files ' not in command(guest, 'ps', b'name=supervisor ')
            report['resources_after'] = resources(guest)
            assert report['resources_after'] == expected
        finally:
            guest.close()
            report['serial_sha256'] = sha(directory / (name + '_serial.log'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('system', 'death-system', 'sdk-build', 'profile', 'dash', 'dash-receipt', 'output'):
        parser.add_argument('--' + field, type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'scope': 'private pre-TLS native files transport to late static glibc'}
    try:
        dash = args.dash.resolve(strict=True)
        dash_receipt = load_json(args.dash_receipt)
        assert dash_receipt['profile'] == 'dash_glibc_preview' and dash_receipt['sha256'] == sha(dash)
        profile, sdk = load_json(args.profile), args.sdk_build.resolve(strict=True)
        report['profile_sha256'] = sha(args.profile)
        report['sdk_manifest_sha256'] = sha(sdk / 'manifest.json')
        report['dash_elf_sha256'] = sha(dash)
        report['dash_receipt_sha256'] = sha(args.dash_receipt)
        elf, binding = build_fixture(sdk, profile, out, report)
        for name, system, death in [('healthy', args.system, False),
                                    ('service_exit', args.death_system, True)]:
            system = system.resolve(strict=True)
            manifest = bind_system(system)
            assert manifest['glibc_files_death_probe'] is death
            result = report[name] = {'build_id': manifest['build_id'],
                                     'system_manifest_sha256': sha(system / 'manifest.json'),
                                     'iso_sha256': sha(system / 'xos-install.iso')}
            guest_case(system, dash, elf, out, result, death)
            assert bind_system(system) == manifest
        assert verify_profile(load_json(args.profile), 'glibc', sdk) == binding
        assert sha(args.profile) == report['profile_sha256']
        assert sha(args.dash_receipt) == report['dash_receipt_sha256']
        assert sha(dash) == report['dash_elf_sha256'] and sha(elf) == report['elf_sha256']
        assert all(sha(ROOT / path) == digest for path, digest in report['source_sha256'].items())
        report['status'] = 'passed_subset'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        write_report(out / 'report.json', report)
    print(report['status'])


if __name__ == '__main__':
    main()
