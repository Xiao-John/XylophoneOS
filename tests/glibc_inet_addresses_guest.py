#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run independent C and C++ network address programs on a normal XOS image."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_smoke import Guest
from build_glibc_program import verify_elf
from build_glibc_sdk import inputs as sdk_inputs, sha
from glibc_g1_probe import clean_build_environment, tool_identity
from glibc_static_guest import system_sources
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes
from work_disk import transfer
from xypm_format import require
from xypm_sdk_profile import metadata_snapshot, verify_profile

FIXTURES = ROOT / 'tests/fixtures/glibc_inet'
SHARED = ROOT / 'src/shared/include'
CASES = (('c', 'gcc', 'c11', b'GLIBC_INET_C_PASS layout bytes symbols ipv6'),
         ('cpp', 'g++', 'gnu++20', b'GLIBC_INET_CXX_PASS layout bytes symbols ipv6 net2'))


def compile_fixtures(args, sdk, report):
    profile, profile_hash = metadata_snapshot(args.profile)
    binding = verify_profile(profile, 'glibc', args.sdk)
    require(sdk['inputs'] == sdk_inputs(), 'static SDK source snapshot changed')
    stubs = set(sdk['stub_functions'])
    require({'socket', 'connect', 'poll'} <= stubs, 'SDK socket/readiness boundary changed')
    require(not {'htonl', 'htons', 'ntohl', 'ntohs'} & stubs, 'byte-order functions must be real')
    report.update(profile=binding, profile_sha256=profile_hash,
                  installed_headers={name: sdk['artifacts'][name] for name in
                                     ('usr/include/netinet/in.h', 'usr/include/bits/in.h')})
    expected_source = [FIXTURES / ('addresses.' + suffix) for suffix in ('h', 'c', 'cpp')]
    expected_source += [SHARED / 'xos' / name for name in ('abi_types.hpp', 'net_service_abi.hpp')]
    sources = {str(path.relative_to(ROOT)): sha(path) for path in expected_source}
    report['sources'] = sources
    tools = {name: tool_identity('x86_64-elf-' + name) for name in ('gcc', 'g++', 'as', 'ld')}
    for name, identity in tools.items():
        require(identity.get('available') and identity['sha256'] == sdk['tools']['x86_64-elf-' + name]['sha256'],
                'target tool differs from the SDK: ' + name)
    report['tools'] = {name: identity['sha256'] for name, identity in tools.items()}
    tools_dir = args.output / 'tools'
    tools_dir.mkdir()
    for name in ('as', 'ld'):
        (tools_dir / name).symlink_to(tools[name]['path'])
    env, _ = clean_build_environment(os.environ)
    env['LC_ALL'] = 'C'
    sysroot = args.sdk / 'sysroot'
    lib = sysroot / 'usr/lib'
    driver = ['--sysroot=' + str(sysroot), '-B' + str(tools_dir) + '/']
    common = ['-O2', '-Wall', '-Wextra', '-Werror', '-mno-red-zone', '-fno-pie', '-fno-pic',
              '-fno-stack-protector', '-fno-builtin', '-nostdinc', '-ftls-model=local-exec',
              '-isystem', str(sysroot / 'usr/include'), '-isystem', str(lib / 'compiler-include')]
    start = ('xos_start.o', 'crti.o', 'crtbegin.o', 'xos_start_c.o')
    end = ('crtend.o', 'crtn.o')
    archives = ('libc.a', 'libm.a', 'libxos_terminal.a', 'libgcc.a', 'libgcc_eh.a')
    programs = {}
    for language, compiler, standard, _ in CASES:
        options = ['-D_POSIX_C_SOURCE=200809L'] if language == 'c' else [
            '-nostdinc++', '-fno-rtti', '-fno-exceptions', '-I', str(SHARED)]
        obj = args.output / (language + '.o')
        program = args.output / (language + '.elf')
        with (args.output / (language + '-build.log')).open('wb') as log:
            subprocess.run([tools[compiler]['path'], *driver, *common, '-std=' + standard, *options,
                            '-c', FIXTURES / f'addresses.{language}', '-o', obj],
                           check=True, env=env, stdout=log, stderr=subprocess.STDOUT)
            subprocess.run([tools[compiler]['path'], *driver, '-nostdlib', '-static', '-no-pie',
                            '-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096',
                            '-T', sysroot / 'user.ld', '-o', program, *(lib / name for name in start), obj,
                            '-Wl,--start-group', *(lib / name for name in archives
                                                  if 'usr/lib/' + name in profile['sdk_binding']['link_artifacts']),
                            '-Wl,--end-group', *(lib / name for name in end)],
                           check=True, env=env, stdout=log, stderr=subprocess.STDOUT)
        report['programs'][language] = {'elf_sha256': sha(program), 'object_sha256': sha(obj),
                                        'headers': verify_elf(program)}
        programs[language] = program
    require(all(sha(ROOT / path) == digest for path, digest in sources.items()), 'guest source changed')
    require(verify_profile(profile, 'glibc', args.sdk) == binding and sha(args.profile) == profile_hash,
            'static SDK/profile changed during linking')
    return programs


def run_guest(args, image, programs, report):
    with tempfile.TemporaryDirectory(prefix='xos_inet_') as folder:
        temporary = Path(folder)
        boot = temporary / 'ordinary.iso'
        shutil.copyfile(image, boot)
        require(sha(boot) == report['image_sha256'], 'ISO staging changed its contents')
        disk = temporary / 'work.img'
        create_fat32(disk, 512)
        transfer(disk, 'mkdir', '/bin')
        for name, program in programs.items():
            path = f'/bin/{name}.elf'
            exported = temporary / (name + '-readback.elf')
            transfer(disk, 'import', path, program)
            transfer(disk, 'export', path, exported)
            require(sha(exported) == report['programs'][name]['elf_sha256'], 'ELF changed on FAT disk')

        guest = Guest(boot, 'glibc_inet_addresses', work_disk=disk, network=False, log_dir=args.output)
        try:
            report['qemu_version'] = subprocess.check_output(
                [guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=30)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=40)
            command(guest, 'demo quiet', b'demo tasks')
            command(guest, 'audio stop', b'audio: service stopped')
            baseline = resources(guest)
            report['baseline'] = baseline
            cases = [('exec-file /bin/' + name + '.elf', marker, b'0') for name, _, _, marker in CASES]
            cases.append(('exec libc_hello', b'libc says: malloc+printf 42 beef', b'7'))
            for invocation, marker, exit_code in cases:
                output = command(guest, invocation, b'kind=', timeout=45)
                exits = re.findall(rb'\[wait\] pid=\d+ kind=(\w+) code=(-?\d+)', output)
                require(exits == [(b'exited', exit_code)] and output.count(marker) == 1,
                        invocation + ' returned unexpected results')
                after = resources(guest)
                require(after == baseline, invocation + ' changed the resource baseline')
                report['cases'].append({'command': invocation, 'marker': marker.decode(),
                                        'exit_code': int(exit_code), 'resources_after': after})
        finally:
            guest.close()
            (args.output / 'serial.log').write_bytes(guest.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('sdk', 'profile', 'system', 'system-source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    for name in ('sdk', 'profile', 'system', 'system_source', 'output'):
        setattr(args, name, getattr(args, name).resolve())
    args.output.mkdir(parents=True)
    report = {'status': 'failed', 'programs': {}, 'cases': [], 'runner_sha256': sha(Path(__file__))}
    try:
        system, system_hash = metadata_snapshot(args.system / 'manifest.json')
        sdk, sdk_hash = metadata_snapshot(args.sdk / 'manifest.json')
        image = args.system / 'xos-install.iso'
        image_hash = sha(image)
        require(system_sources(args.system_source) == system['sources'], 'system source snapshot changed')
        require(image_hash == system['artifacts']['xos-install.iso']['sha256'], 'system ISO changed')
        require(not system.get('glibc_files_death_probe'), 'ordinary system required')
        report.update(image_sha256=image_hash, system_build_id=system['build_id'],
                      system_manifest_sha256=system_hash, sdk_manifest_sha256=sdk_hash)
        programs = compile_fixtures(args, sdk, report)
        run_guest(args, image, programs, report)
        report['status'] = 'passed'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
