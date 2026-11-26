# SPDX-License-Identifier: Apache-2.0
"""Qualify the glibc application builder and XPK lifecycle on an isolated FAT disk."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from unittest.mock import patch

from boot_smoke import Guest
from process_smoke import resources
from task_smoke import pump, send_bytes

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from make_work_disk import create_fat32
from xos_app import GLIBC_BUILDER, build
from xypm_format import DEFAULT_PROFILE, canonical, load_json, require, sha_file
from xypm_image import Disk, query_image, transact


def app(profile, *arguments):
    command = [sys.executable, str(ROOT / 'scripts/xos_app.py'), '--profile', str(profile),
               *map(str, arguments)]
    return json.loads(subprocess.check_output(command, text=True))


def rejected_app(profile, diagnostic, *arguments):
    command = [sys.executable, str(ROOT / 'scripts/xos_app.py'), '--profile', str(profile),
               *map(str, arguments)]
    result = subprocess.run(command, capture_output=True, text=True)
    require(result.returncode != 0 and diagnostic in result.stderr, 'unexpected application command result')


def build_while_header_changes(profile, sdk, project, header):
    original = header.read_bytes()
    run = subprocess.run
    edited = False

    def change_live_header(command, *args, **kwargs):
        nonlocal edited
        if isinstance(command, list) and len(command) > 1 and command[1] == str(GLIBC_BUILDER):
            header.write_bytes(b'#error live project header reached the compiler\n')
            edited = True
            try:
                return run(command, *args, **kwargs)
            finally:
                header.write_bytes(original)
        return run(command, *args, **kwargs)

    with patch.object(subprocess, 'run', side_effect=change_live_header):
        receipt = build(project, sdk, load_json(profile))
    require(edited, 'snapshot test did not execute the backend')
    return receipt


def package(work, profile, sdk, language, revision):
    name = 'runtime_' + language
    project = work / f'{name}_{revision}'
    destination = project.with_suffix('.xpk')
    app(profile, 'init', project, '--id', 'friends.' + name, '--language', language)
    definition = project / 'xos_app.json'
    config = load_json(definition)
    config['revision'] = revision
    source = project / config['sources'][0]
    marker = f'XPK_{language.upper()}_R{revision}_OK'
    source.write_text(source.read_text().replace(f'Hello from XOS package: friends.{name}', marker))
    if language == 'cpp':
        header = project / 'src/message.hpp'
        header.write_text('#pragma once\nconst char* package_message();\n')
        component = project / 'src/component'
        component.mkdir()
        extra = component / 'message.cpp'
        extra.write_text(f'#include <message.hpp>\nconst char* package_message() {{ return "{marker}"; }}\n')
        source.write_text('#include <message.hpp>\n' + source.read_text().replace(f'"{marker}"', 'package_message()'))
        config['sources'].append(extra.relative_to(project).as_posix())
    definition.write_bytes(canonical(config))
    if language == 'cpp' and revision == 0:
        original = header.read_bytes()
        (project / 'untracked.hpp').write_text('// intentionally absent from project inputs\n')
        header.write_bytes(b'#include "../untracked.hpp"\n' + original)
        rejected_app(profile, 'glibc application build failed', 'build', project, '--sdk', sdk)
        header.write_bytes(original)
    if language == 'cpp' and revision == 0:
        receipt = build_while_header_changes(profile, sdk, project, header)
        header.write_bytes(original + b'// changed after compile\n')
        rejected_app(profile, 'project inputs changed', 'check', project, '--sdk', sdk)
        header.write_bytes(original)
    else:
        receipt = app(profile, 'build', project, '--sdk', sdk)
    app(profile, 'check', project, '--sdk', sdk)
    packed = app(profile, 'pack', project, '--sdk', sdk, '--output', destination)
    require(receipt['runtime_family'] == 'glibc' and receipt['output_sha256']
            == sha_file(project / receipt['output']), 'wrong runtime or ELF in builder receipt')
    if language == 'cpp':
        require(receipt['inputs']['src/message.hpp'] == sha_file(header), 'local header missing from build receipt')
    require(packed['sha256'] == sha_file(destination), 'wrong package digest in receipt')
    return destination, receipt['output_sha256']


def guest_run(iso, disk, output, phase, commands, evidence):
    guest = Guest(iso, phase, work_disk=disk, iso=True, log_dir=output)
    try:
        guest.expect(b'xos64> ', timeout=40)
        send_bytes(guest, b'run\r')
        guest.expect_supervisor(trace=True, timeout=40)
        pump(guest, 1)
        baseline = resources(guest)
        for command, marker in commands:
            start = len(guest.output)
            send_bytes(guest, command.encode() + b'\r')
            guest.expect_supervisor(start=start, timeout=45)
            data = bytes(guest.output[start:])
            statuses = re.findall(rb'kind=exited code=(-?\d+)', data)
            require(marker.encode() in data and statuses and statuses[-1] == b'0',
                    f'{phase}: wrong output or exit for {command}: {data[-1500:]!r}')
            require(resources(guest) == baseline, f'{phase}: resource drift after {command}')
            evidence.append({'phase': phase, 'command': command, 'marker': marker,
                             'baseline': baseline})
    finally:
        guest.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'dash', 'dash-receipt', 'sdk-build', 'profile', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True)
    iso = args.system / 'xos-install.iso'
    system_manifest = args.system / 'manifest.json'
    system = load_json(system_manifest)
    sdk_manifest = args.system / 'sdk/manifest.json'
    dash = load_json(args.dash_receipt)
    require(sha_file(iso) == system['artifacts']['xos-install.iso']['sha256'], 'system ISO hash mismatch')
    require(dash['sha256'] == sha_file(args.dash) and dash['sdk_manifest_sha256'] == sha_file(sdk_manifest),
            'dash does not match its receipt or the system SDK')
    profile = load_json(args.profile)
    require(profile['runtime_family'] == 'glibc' and 'cxx_runtime' in profile['features'],
            'qualification needs a glibc C/C++ profile')
    evidence = {'status': 'failed', 'build_id': system['build_id'], 'iso_sha256': sha_file(iso),
                'system_manifest_sha256': sha_file(system_manifest), 'dash_sha256': dash['sha256'],
                'system_sdk_sha256': sha_file(sdk_manifest), 'profile_sha256': sha_file(args.profile),
                'application_sdk_sha256': sha_file(args.sdk_build / 'manifest.json'),
                'qemu_version': subprocess.check_output(['qemu-system-x86_64', '--version'], text=True).splitlines()[0],
                'runner_sha256': sha_file(__file__), 'checks': [], 'transactions': []}
    try:
        with tempfile.TemporaryDirectory(prefix='glibc_xpk_') as folder:
            work = Path(folder)
            c, c_elf = package(work, args.profile, args.sdk_build, 'c', 0)
            cpp, cpp_elf = package(work, args.profile, args.sdk_build, 'cpp', 0)
            update, update_elf = package(work, args.profile, args.sdk_build, 'cpp', 1)
            evidence['checks'].extend([
                {'phase': 'host', 'check': 'untracked_include_rejected'},
                {'phase': 'host', 'check': 'temporary_live_header_change_uses_snapshot'},
                {'phase': 'host', 'check': 'changed_local_header_requires_rebuild'},
            ])
            evidence['packages'] = {p.name: {'xpk_sha256': sha_file(p), 'elf_sha256': elf}
                                    for p, elf in ((c, c_elf), (cpp, cpp_elf), (update, update_elf))}
            source = work / 'source.img'
            create_fat32(source, 512)
            user = work / 'user.txt'
            user.write_bytes(b'Unmanaged file survives glibc package transactions.\n')
            with Disk(source, work) as disk:
                for directory in ('/usr', '/usr/bin', '/tests'):
                    disk.command('mkdir', directory)
                disk.command('import', '/usr/bin/dash', args.dash)
                disk.command('import', '/user.txt', user)
                for name, text in (('c', '/usr/bin/runtime_c\n'), ('cpp', '/usr/bin/runtime_cpp\n'),
                                   ('removed', 'test ! -e /usr/bin/runtime_cpp && echo XPK_CPP_REMOVED_OK\n')):
                    script = work / (name + '.sh')
                    script.write_text(text)
                    disk.command('import', '/tests/' + name + '.sh', script)
            untouched = sha_file(source)
            rejected = work / 'wrong-profile.img'
            try:
                transact(source, rejected, load_json(DEFAULT_PROFILE), 'install', package=c)
            except ValueError as error:
                require('target profile mismatch' in str(error), 'wrong reason for foreign profile rejection')
            else:
                raise AssertionError('newlib profile installed a glibc XPK')
            require(not rejected.exists() and sha_file(source) == untouched, 'rejected install changed disk state')
            evidence['checks'].append({'phase': 'host', 'check': 'newlib_rejected_glibc_xpk'})

            def change(before, name, operation, **inputs):
                after = work / (name + '.img')
                result = transact(before, after, profile, operation, **inputs)
                evidence['transactions'].append({'operation': operation, 'sha256': sha_file(after)})
                require(result['status'] == 'exported_candidate', f'{name}: transaction did not publish')
                query_image(after, profile, 'verify-installed')
                return after

            installed_c = change(source, 'c', 'install', package=c)
            installed = change(installed_c, 'both', 'install', package=cpp)
            c_commands = [('exec-file /usr/bin/runtime_c', 'XPK_C_R0_OK'),
                          ('dash /tests/c.sh', 'XPK_C_R0_OK')]
            guest_run(iso, installed, output, 'install', c_commands +
                      [('exec-file /usr/bin/runtime_cpp', 'XPK_CPP_R0_OK'),
                       ('dash /tests/cpp.sh', 'XPK_CPP_R0_OK')], evidence['checks'])
            upgraded = change(installed, 'upgraded', 'upgrade', package=update)
            guest_run(iso, upgraded, output, 'upgrade',
                      [('exec-file /usr/bin/runtime_cpp', 'XPK_CPP_R1_OK'),
                       ('dash /tests/cpp.sh', 'XPK_CPP_R1_OK')], evidence['checks'])
            removed = change(upgraded, 'cpp_removed', 'remove', package_id='friends.runtime_cpp')
            guest_run(iso, removed, output, 'remove', c_commands +
                      [('dash /tests/removed.sh', 'XPK_CPP_REMOVED_OK')], evidence['checks'])
            empty = change(removed, 'all_removed', 'remove', package_id='friends.runtime_c')
            require(query_image(empty, profile, 'verify-installed')['files'] == 0, 'managed files remain')
            with Disk(empty, work, True) as disk:
                require(disk.export('/user.txt').read_bytes() == user.read_bytes(), 'unmanaged file changed')
                require(disk.info('/usr/bin/runtime_c') is None and disk.info('/usr/bin/runtime_cpp') is None,
                        'a removed executable remains')
            require(sha_file(source) == untouched, 'lifecycle changed source image')
            evidence['checks'].append({'phase': 'host', 'check': 'source_and_unmanaged_data_preserved'})
            evidence['status'] = 'passed'
    except Exception as error:
        evidence['error'] = str(error)
        raise
    finally:
        (output / 'report.json').write_bytes(canonical(evidence))


if __name__ == '__main__':
    main()
