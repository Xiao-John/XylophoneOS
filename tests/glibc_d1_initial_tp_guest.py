#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the actual GNU shared rtld initial NPTL thread handoff in XOS."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

from boot_smoke import Guest
from build_glibc_program import verify_elf
from build_glibc_sdk import inputs as sdk_inputs
from glibc_g1_probe import clean_build_environment, tool_identity
from make_work_disk import create_fat32
from process_smoke import command, resources
from shell_launch_support import bind_system, check_hash, relative_file, sha, write_report
from task_smoke import send_bytes
from work_disk import transfer
from xypm_format import load_json
from xypm_sdk_profile import verify_profile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/glibc_d1/initial_tls_guest.c'
OBJECTS = ('d1-initial-tp-fixture.o', 'rtld.os', 'dl-tls_init_tp.os', 'dl-mutex.os',
           'dl-minimal-malloc.os', 'xos_rtld_heap.os')
SUCCESS = (b'D1_INITIAL_TP_OK tcb=gnu tid=native stack=exact '
           b'dtv=preserved dispatch=preserved')


def build(args, report, rtld):
    objects = [args.rtld_proof / 'shared/elf' / name for name in OBJECTS]
    if not all(str(obj.relative_to(args.rtld_proof)) in rtld['artifacts'] for obj in objects):
        raise ValueError('rtld manifest is missing a TP fixture input')
    tool_names = tuple('x86_64-elf-' + name for name in ('ld', 'objcopy', 'nm'))
    tools = {name: tool_identity(name) for name in tool_names}
    for name, tool in tools.items():
        if tool['sha256'] != rtld['tools'][name]['sha256']:
            raise ValueError('rtld tool changed: ' + name)
    report['tools'] = tools
    env, report['sanitized_environment'] = clean_build_environment(os.environ)
    env['LC_ALL'] = 'C'
    output = args.output

    def run(name, argv):
        argv = list(map(str, argv))
        report['commands'][name] = argv
        with (output / (name + '.log')).open('w') as log:
            subprocess.run(argv, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)

    fixture, gnu_rtld, *runtime = objects
    # Use the writable GNU rtld state. Only its full interpreter entry symbol
    # must be private to the input object, so the native harness CRT can enter.
    state = output / 'rtld-local-entry.o'
    run('localize_entry', [tools['x86_64-elf-objcopy']['path'], '--localize-symbol=_start',
                           gnu_rtld, state])
    sysroot = args.sdk_build / 'sysroot'
    elf = output / 'initial_tp.elf'
    run('link_guest', [tools['x86_64-elf-ld']['path'], '--gc-sections', '-z', 'noexecstack',
                       '-z', 'max-page-size=4096', '--build-id=none', '-Map', output / 'link.map',
                       '-T', sysroot / 'user.ld', sysroot / 'usr/lib/xos_start.o',
                       fixture, state, *runtime, '-o', elf])
    run('undefined', [tools['x86_64-elf-nm']['path'], '-u', elf])
    if (output / 'undefined.log').stat().st_size:
        raise ValueError('TP fixture has unresolved external dependencies')
    report['program_headers'] = verify_elf(elf)
    report['guest_elf_sha256'] = sha(elf)
    return elf


def exercise(args, report, elf):
    with tempfile.TemporaryDirectory(prefix='xos_d1_initial_tp_') as folder:
        disk = Path(folder) / 'work.img'
        create_fat32(disk, 512)
        transfer(disk, 'mkdir', '/bin')
        transfer(disk, 'import', '/bin/initial_tp', elf)
        guest = Guest(args.system / 'xos-install.iso', 'initial_tp', work_disk=disk,
                      qmp_enabled=False, log_dir=args.output)
        try:
            report['qemu_command'] = guest.command
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'],
                                                             text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=90)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=90)
            command(guest, 'demo quiet', b'demo tasks')
            baseline = resources(guest)
            report.update(resources_before=baseline, runs=[])
            for _ in range(2):
                result = command(guest, 'exec-file /bin/initial_tp', b'kind=exited code=', timeout=40)
                after = resources(guest)
                report['runs'].append({'output': result.decode(errors='replace'), 'resources_after': after})
                if (SUCCESS not in result or after != baseline
                        or re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', result) != [b'0']):
                    raise AssertionError('native initial TP handoff failed: ' + repr(result))
        finally:
            guest.close()
            report['serial_sha256'] = sha(args.output / 'initial_tp_serial.log')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'sdk-build', 'profile', 'rtld-proof', 'output'):
        parser.add_argument('--' + name, type=lambda value: Path(value).resolve(), required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True)
    report = {'status': 'failed', 'scope': 'GNU initial thread TP handoff with prepared storage',
              'shared_interpreter_executed': False, 'commands': {}}
    try:
        system = bind_system(args.system)
        profile = load_json(args.profile)
        sdk = verify_profile(profile, 'glibc', args.sdk_build)
        sdk_manifest = args.sdk_build / 'manifest.json'
        manifest_path = args.rtld_proof / 'manifest.json'
        rtld = load_json(manifest_path)
        prep_path = args.rtld_proof / 'prepared/manifest.json'
        prepared = load_json(prep_path)
        if (rtld['status'] != 'rtld_entry_compiled_startup_blocked'
                or prepared['source_verification']['status'] != 'upstream_signature_verified'
                or sdk_inputs() != prepared['inputs']
                or prepared['inputs'] != load_json(sdk_manifest)['inputs']
                or rtld['source_sha256'] != load_json(sdk_manifest)['source_sha256']):
            raise ValueError('rtld and SDK are outside the same authenticated source closure')
        check_hash(prep_path, rtld['preparation_manifest_sha256'], 'rtld preparation')
        check_hash(FIXTURE, rtld['initial_tp_fixture_sha256'], 'TP fixture source')
        artifacts = {relative_file(args.rtld_proof, Path(name)): digest
                     for name, digest in rtld['artifacts'].items()}
        for path, digest in artifacts.items():
            check_hash(path, digest, 'rtld object')
        report.update(build_id=system['build_id'], iso_sha256=sha(args.system / 'xos-install.iso'),
                      system_manifest_sha256=sha(args.system / 'manifest.json'),
                      sdk_sha256=sha(sdk_manifest), profile_sha256=sha(args.profile),
                      rtld_manifest_sha256=sha(manifest_path), rtld_objects=rtld['artifacts'])
        elf = build(args, report, rtld)
        exercise(args, report, elf)
        if (bind_system(args.system) != system or verify_profile(load_json(args.profile), 'glibc', args.sdk_build) != sdk
                or sha(manifest_path) != report['rtld_manifest_sha256']
                or sha(elf) != report['guest_elf_sha256']
                or any(sha(path) != digest for path, digest in artifacts.items())):
            raise ValueError('bound acceptance inputs changed during the guest run')
        report['status'] = 'passed_subset'
    finally:
        write_report(args.output / 'report.json', report)
    print(report['status'])


if __name__ == '__main__':
    main()
