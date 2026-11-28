#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Cold-boot a new 1024 fixture, selected GNU C/C++, rollback, and restoration."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_candidate import inspect_app_kit
from glibc_newlib_frozen_rollback_guest import executable, readback, seed_disk, verify_release_file
from make_work_disk import create_fat32
from package_application_preview import FROZEN_PROFILE, FROZEN_RELEASE
from package_p2_faults import sparse_copy
from prepare_frozen_rollback import SEED as FROZEN_SEED
from shell_launch_support import bind_system
from task_smoke import pump, send_bytes
from work_disk import host_tool as fat_tool
from xos_sdk import inspect as inspect_sdk
from xypm_format import canonical, load_json, require, sha_file
from xypm_image import host_tool as xypm_tool

GLIBC_SEED = b'p0-r1-glibc-user-data\n'


def cold_boot(out, image, disk, name, build_id, invocations, historical=False):
    guest = Guest(image, name, cpu='qemu64' if historical else 'qemu64,+rdrand',
                  iso=not historical, work_disk=disk, qmp_enabled=False, log_dir=out)
    prompt = b'sup> ' if historical else b'xsh> '
    result = {'build_id': build_id, 'qemu_command': guest.command, 'programs': []}

    def command(line, marker, timeout=45):
        start = len(guest.output)
        send_bytes(guest, line.encode() + b'\r')
        guest.expect(marker, start=start, timeout=timeout)
        guest.expect(prompt, start=guest.output.index(marker, start), timeout=45)
        return bytes(guest.output[start:])

    def resources():
        output = command('stats', b'[resources] free=')
        match = re.search(rb'free=(\d+) tasks=(\d+) completions=(\d+)', output)
        require(match is not None, 'guest omitted resource counters')
        return tuple(map(int, match.groups()))

    try:
        guest.expect(b'xos64> ', timeout=60)
        require(b'build=' + build_id.encode() in guest.output, 'cold boot reported a different build ID')
        start = len(guest.output)
        send_bytes(guest, b'run\r')
        guest.expect(prompt, start=start, timeout=60)
        if not historical:
            guest.expect_supervisor(trace=True, start=start, timeout=30)
        command('demo quiet', b'demo tasks')
        if not historical:
            command('audio stop', prompt)
            pump(guest, 0.2)
        baseline = resources()
        result['resources_before'] = baseline
        for invocation, marker in invocations:
            output = command(invocation, b'kind=exited code=', timeout=120)
            exits = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', output)
            require(marker in output and exits == [b'0'], 'fixture output or ordinary exit differs')
            after = resources()
            require(after == baseline, 'ordinary fixture did not reclaim exact resources')
            result['programs'].append({'command': invocation, 'marker': marker.decode(),
                                       'exit_code': 0, 'resources_after': after})
        command('sync', b'[files] sync=ok')
        result['status'] = 'passed'
        return result
    finally:
        guest.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('frozen-preparation', 'kit', 'candidate', 'system-source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('sdk-manifest-sha256', 'sdk-tree-sha256', 'profile-sha256'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    prepared, kit, candidate, source = (path.resolve(strict=True) for path in
        (args.frozen_preparation, args.kit, args.candidate, args.system_source))
    out = args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    names = ['tests/sdk_frozen_roundtrip_guest.py', 'tests/prepare_frozen_rollback.py',
             'tests/glibc_newlib_frozen_rollback_guest.py', 'tests/boot_smoke.py',
             'tests/package_p2_faults.py', 'tests/shell_launch_support.py',
             'tests/task_smoke.py', 'tests/process_smoke.py', 'tests/kernel_smoke.py',
             'tests/fixtures/sdk_rollback/frozen.c', 'tests/fixtures/sdk_rollback/glibc_c.c',
             'tests/fixtures/sdk_rollback/glibc_cpp.cpp', 'LICENSE',
             'docs/releases/release_0_0_1_1024.json', 'config/package/xos_x86_64_static_single_v1.json']
    names += [str(path.relative_to(ROOT)) for path in sorted((ROOT / 'scripts').rglob('*.py'))]
    # Bind transitive imported helpers too, including the FAT manipulation
    # implementations whose compiled tools create and read the offline disks.
    for module in tuple(sys.modules.values()):
        location = getattr(module, '__file__', None)
        if location:
            path = Path(location).resolve()
            if path.is_relative_to(ROOT) and path.suffix == '.py':
                names.append(str(path.relative_to(ROOT)))
    names += ['scripts/work_disk_host.cpp', 'scripts/xypm_disk_host.cpp',
              'src/third_party/fatfs/ff.c', 'src/user/services/fatfs_unicode.cpp']
    names += [str(path.relative_to(ROOT)) for path in (ROOT / 'src/third_party/fatfs').glob('*.h')]
    names = sorted(set(names))
    source_hashes = lambda: {name: sha_file(ROOT / name) for name in names}
    report = {'status': 'failed', 'sources': source_hashes(), 'commands': [], 'guards': [], 'guests': {}}
    state = out / 'selection.json'
    selector = [sys.executable, ROOT / 'scripts/xos_sdk.py', '--state', state]

    def run(parts, label, reject=None):
        command = list(map(str, parts))
        result = subprocess.run(command, capture_output=True, text=True, timeout=240)
        (out / (label + '.log')).write_text(result.stdout + result.stderr)
        report['commands'].append({'command': command, 'log': label + '.log',
                                   'returncode': result.returncode, 'expected_rejection': reject})
        if reject is None:
            require(result.returncode == 0, label + ': ' + result.stderr)
        else:
            require(result.returncode != 0 and reject in result.stderr, label + ': ' + result.stderr)
            report['guards'].append(label)
        return json.loads(result.stdout) if result.stdout.startswith('{') else result.stdout

    def selected(parts, label, reject=None):
        return run([*selector, *parts], label, reject)

    def verify_user(disk, expected):
        actual = readback(disk, '/state/user.txt', out / 'readback.txt')
        require(actual == expected, 'cold boot failed to preserve and append user data')
        return hashlib.sha256(actual).hexdigest()

    try:
        before = load_json(prepared / 'report.json')
        require(before['status'] == 'prepared_guest_not_run' and before['guest'] == 'not_run',
                'frozen preparation must be a freshly built, unbooted fixture')
        require(all(sha_file(ROOT / name) == digest for name, digest in before['sources'].items()),
                'frozen preparation source changed')
        require(all(sha_file(prepared / name) == digest for name, digest in before['artifacts'].items()),
                'frozen preparation artifact changed')
        require(all(sha_file(Path(name)) == digest for name, digest in before['input_artifacts'].items()),
                'an original frozen release artifact changed')
        release = load_json(FROZEN_RELEASE)
        boot, original_sdk = Path(before['boot']), Path(before['sdk'])
        verify_release_file(release, boot, '_boot.img')
        require(inspect_sdk('newlib', original_sdk) == before['sdk_binding'], 'frozen SDK binding changed')
        binding = inspect_app_kit(kit)
        require(binding['sdk_manifest_sha256'] == args.sdk_manifest_sha256 and
                binding['sdk_tree_sha256'] == args.sdk_tree_sha256 and
                binding['profile_sha256'] == args.profile_sha256, 'independent GNU SDK anchors differ')
        candidate_file = candidate / 'candidate_manifest.json'
        candidate_report = load_json(candidate_file)
        require(candidate_report['installer_guest_qualification'] == 'passed' and
                candidate_report['application_sdk'] == binding, 'qualified candidate SDK binding differs')
        require(all(sha_file(candidate / name) == digest for name, digest in candidate_report['artifacts'].items()),
                'candidate artifacts differ from its manifest')
        stock = load_json(candidate / 'stock_guest/report.json')
        system = candidate / 'system'
        native = bind_system(system, source)
        require(stock['status'] == 'passed' and stock['system_build_id'] == native['build_id'] and
                native['build_id'] == candidate_report['build_id'] and
                stock['image_sha256'] == sha_file(system / 'xos-install.iso'), 'stock guest candidate identity differs')
        protected = {str(path): sha_file(path) for path in
                     (prepared / 'report.json', prepared / before['disk'], prepared / before['package'],
                      candidate_file, system / 'manifest.json', system / 'xos-install.iso')}
        report.update(frozen_preparation_sha256=sha_file(prepared / 'report.json'),
                      frozen=before, candidate_manifest_sha256=sha_file(candidate_file),
                      candidate_source_commit=candidate_report['source_commit'],
                      current_build_id=native['build_id'], current_system_sources=native['sources'],
                      current_iso_sha256=sha_file(system / 'xos-install.iso'), sdk_binding=binding,
                      protected_inputs=protected,
                      qemu_version=subprocess.check_output(['qemu-system-x86_64', '--version'], text=True).splitlines()[0])

        configured, old_sdk = out / 'configured-kit', out / 'configured-newlib'
        ignore = shutil.ignore_patterns('__pycache__', '*.pyc', '.cache')
        shutil.copytree(kit, configured, ignore=ignore)
        shutil.copytree(original_sdk, old_sdk, ignore=ignore)
        require(inspect_app_kit(configured) == binding, 'copied GNU kit differs')
        old_binding = inspect_sdk('newlib', old_sdk)
        require({key: value for key, value in old_binding.items() if key != 'root'} ==
                {key: value for key, value in before['sdk_binding'].items() if key != 'root'}, 'copied frozen SDK differs')
        initial = selected(['setup', '--glibc-kit', configured, '--newlib-sdk', old_sdk], 'registry_setup')
        require(initial['active'] == 'glibc', 'initial SDK selection differs')
        selected_hash = sha_file(state)
        selected(['setup', '--glibc-kit', configured, '--newlib-sdk', old_sdk], 'registry_setup_existing', 'File exists')
        require(sha_file(state) == selected_hash, 'repeated setup changed selection')
        report['registry_bindings'] = initial['bindings']
        profile = configured / 'profile.json'
        packages, applications = {}, {}
        for language in ('c', 'cpp'):
            project = out / ('project-' + language)
            selected(['app', 'init', project, '--id', 'rollback.glibc_' + language, '--language', language], language + '_init')
            suffix = 'c' if language == 'c' else 'cpp'
            shutil.copyfile(ROOT / ('tests/fixtures/sdk_rollback/glibc_' + language + '.' + suffix), project / ('src/main.' + suffix))
            metadata = load_json(project / 'xos_app.json')
            metadata['required_features'] += ['file_io', 'static_tls'] if language == 'c' else ['file_io', 'threads']
            (project / 'xos_app.json').write_bytes(canonical(metadata))
            for operation in ('build', 'check'):
                selected(['app', operation, project], language + '_' + operation)
            packages[language] = out / (language + '.xpk')
            selected(['app', 'pack', project, '--output', packages[language]], language + '_pack')
            applications[language] = executable(packages[language], profile, '/usr/bin/glibc_' + language, binding=binding)
        report['applications'] = applications
        selected(['app', 'check', out / 'project-c', '--s', old_sdk], 'reject_app_sdk_override', 'supplies its own')
        selected(['xypm', 'verify', prepared / before['package'], '--prof', FROZEN_PROFILE],
                 'reject_profile_override', 'supplies its own')

        old_disk, new_disk, blank, intermediate = (out / name for name in
            ('frozen-work.img', 'glibc-work.img', 'blank.img', 'glibc-c.img'))
        sparse_copy(prepared / before['disk'], old_disk)
        require(sha_file(old_disk) == before['artifacts'][before['disk']], 'frozen working copy differs')
        create_fat32(blank, 512)
        blank_hash = sha_file(blank)
        for language, input_disk, output_disk in (('c', blank, intermediate), ('cpp', intermediate, new_disk)):
            run([sys.executable, ROOT / 'scripts/xypm.py', 'install', packages[language], '--profile', profile,
                 '--offline', '--image', input_disk, '--output-image', output_disk], language + '_initialize_disk')
        require(sha_file(blank) == blank_hash, 'explicit disk initialization changed its input')
        intermediate.unlink()
        seed_disk(new_disk, out / 'seed.txt', GLIBC_SEED)
        verify_user(new_disk, GLIBC_SEED)
        verify_user(old_disk, FROZEN_SEED)
        selected(['xypm', 'verify-installed', '--image', new_disk], 'glibc_database_verified')
        selected(['xypm', 'verify', prepared / before['package']], 'glibc_rejects_frozen_package', 'package target profile mismatch')
        selected(['xypm', 'verify-installed', '--image', old_disk], 'glibc_rejects_frozen_database', 'database profile mismatch')
        old_installed = sha_file(old_disk)
        mixed = out / 'refused-mixed.img'
        selected(['xypm', 'install', packages['c'], '--offline', '--image', old_disk, '--output-image', mixed],
                 'glibc_rejects_frozen_transaction', 'database profile mismatch')
        require(not mixed.exists() and sha_file(old_disk) == old_installed,
                'cross-profile transaction changed the frozen disk or produced output')
        selected(['xypm', 'list', '--image', blank], 'reject_unmarked_list', 'work disk has no xypm profile')
        refused = out / 'refused.img'
        selected(['xypm', 'install', packages['c'], '--offline', '--image', blank, '--output-image', refused],
                 'reject_unmarked_install', 'work disk has no xypm profile')
        repository, lock = out / 'repository', out / 'lock.json'
        selected(['xypm', 'repo-create', packages['c'], '-o', repository], 'repository_create')
        selected(['xypm', 'repo-lock', repository, applications['c']['package_sha256'],
                  '-o', lock], 'repository_lock')
        selected(['xypm', 'repo-install', repository, lock, applications['c']['id'], '--offline',
                  '--image', blank, '--output-image', refused], 'reject_unmarked_repository', 'work disk has no xypm profile')
        require(not refused.exists() and sha_file(blank) == blank_hash, 'unmarked rejection produced output or changed input')
        blank.unlink()

        selected(['use', 'newlib'], 'initial_frozen_selection')
        frozen_project = out / 'project-frozen'
        shutil.copytree(prepared / before['project'], frozen_project, ignore=shutil.ignore_patterns('build'))
        selected(['app', 'build', frozen_project], 'frozen_build_before')
        selected(['app', 'pack', frozen_project, '--output', out / 'frozen-before.xpk'], 'frozen_pack_before')
        rebuilt = executable(out / 'frozen-before.xpk', FROZEN_PROFILE, '/usr/bin/frozen1024')
        require(all(rebuilt[key] == before['application'][key] for key in
                    ('elf_sha256', 'project_inputs', 'sdk_tree_sha256', 'compiler_sha256')),
                'selected frozen SDK did not reproduce the new fixture')
        report['guests']['01_frozen_before'] = cold_boot(out, boot, old_disk, '01_frozen_before',
            release['system_build_id'], [('exec-file /usr/bin/frozen1024 before', b'P0_R1_FROZEN_OK before')], True)
        verify_user(old_disk, FROZEN_SEED + b'before\n')
        old_before = sha_file(old_disk)
        new_before = sha_file(new_disk)
        selected(['use', 'glibc'], 'select_glibc')
        require(sha_file(state) == selected_hash and sha_file(old_disk) == old_before and sha_file(new_disk) == new_before,
                'SDK selection changed a disk or the bound state')

        def current_commands(phase):
            return [('exec-file /usr/bin/glibc_c ' + phase, ('P0_R1_GLIBC_C_OK ' + phase).encode()),
                    ('exec-file /usr/bin/glibc_cpp ' + phase, ('P0_R1_GLIBC_CPP_OK ' + phase).encode())]

        report['guests']['02_glibc_selected'] = cold_boot(out, system / 'xos-install.iso', new_disk,
            '02_glibc_selected', native['build_id'], current_commands('selected'))
        verify_user(new_disk, GLIBC_SEED + b'c-selected\ncpp-selected\n')
        require(sha_file(old_disk) == old_before, 'running the selected SDK changed the frozen disk')
        new_selected = sha_file(new_disk)

        unavailable = out / 'unavailable-kit'
        configured.rename(unavailable)
        try:
            selected(['status'], 'missing_selected_kit_fails_closed', 'SDK must be a real directory')
            require(sha_file(state) == selected_hash, 'failed status changed selection')
            selected(['use', 'newlib'], 'rollback_without_glibc_kit')
            rolled_back = sha_file(state)
            selected(['use', 'glibc'], 'missing_kit_selection_fails_closed', 'SDK must be a real directory')
            require(sha_file(state) == rolled_back and sha_file(old_disk) == old_before and sha_file(new_disk) == new_selected,
                    'failed selection changed state or disks')
            selected(['xypm', 'verify', packages['c']], 'newlib_rejects_glibc_package', 'package target profile mismatch')
            selected(['xypm', 'verify-installed', '--image', new_disk], 'newlib_rejects_glibc_database', 'database profile mismatch')
            selected(['xypm', 'install', prepared / before['package'], '--offline', '--image', new_disk,
                      '--output-image', mixed], 'newlib_rejects_glibc_transaction', 'database profile mismatch')
            require(not mixed.exists() and sha_file(new_disk) == new_selected,
                    'cross-profile rollback transaction changed the GNU disk or produced output')
            selected(['xypm', 'verify-installed', '--image', old_disk], 'frozen_database_verified')
            selected(['app', 'build', frozen_project], 'frozen_build_after')
            selected(['app', 'pack', frozen_project, '--output', out / 'frozen-after.xpk'], 'frozen_pack_after')
            require(sha_file(out / 'frozen-after.xpk') == sha_file(out / 'frozen-before.xpk'),
                    'rollback SDK did not reproduce its package byte for byte')
            report['guests']['03_frozen_rollback'] = cold_boot(out, boot, old_disk, '03_frozen_rollback',
                release['system_build_id'], [('exec-file /usr/bin/frozen1024 rollback', b'P0_R1_FROZEN_OK rollback')], True)
            verify_user(old_disk, FROZEN_SEED + b'before\nrollback\n')
        finally:
            unavailable.rename(configured)
        old_final = sha_file(old_disk)
        unavailable_old = out / 'unavailable-newlib'
        old_sdk.rename(unavailable_old)
        try:
            selected(['use', 'glibc'], 'missing_rollback_sdk_fails_closed', 'SDK must be a real directory')
            require(sha_file(state) == rolled_back, 'missing rollback SDK changed selection')
        finally:
            unavailable_old.rename(old_sdk)
        selected(['use', 'glibc'], 'restore_glibc')
        require(sha_file(state) == selected_hash and sha_file(old_disk) == old_final and sha_file(new_disk) == new_selected,
                'restoration changed SDK binding or independent disks')
        report['guests']['04_glibc_restored'] = cold_boot(out, system / 'xos-install.iso', new_disk,
            '04_glibc_restored', native['build_id'], current_commands('restored'))
        new_data = GLIBC_SEED + b'c-selected\ncpp-selected\nc-restored\ncpp-restored\n'
        report['final_user_data'] = {'glibc': verify_user(new_disk, new_data),
                                   'newlib': verify_user(old_disk, FROZEN_SEED + b'before\nrollback\n')}
        require(sha_file(old_disk) == old_final, 'restored GNU guest changed frozen disk')
        selected(['xypm', 'verify-installed', '--image', new_disk], 'restored_glibc_database_verified')
        for language, application in applications.items():
            require(hashlib.sha256(readback(new_disk, '/usr/bin/glibc_' + language, out / 'readback.elf')).hexdigest()
                    == application['elf_sha256'], 'installed GNU fixture differs from package')
        require(hashlib.sha256(readback(old_disk, '/usr/bin/frozen1024', out / 'readback.elf')).hexdigest()
                == before['application']['elf_sha256'], 'installed frozen fixture differs from package')
        run([sys.executable, ROOT / 'scripts/xypm.py', 'verify-installed', '--profile', FROZEN_PROFILE,
             '--image', old_disk], 'final_frozen_database_verified')
        require(bind_system(system, source) == native and inspect_app_kit(kit) == binding and
                inspect_app_kit(configured) == binding and inspect_sdk('newlib', original_sdk) == before['sdk_binding'],
                'system or SDK inputs changed during the roundtrip')
        require(all(sha_file(Path(name)) == digest for name, digest in protected.items()) and
                all(sha_file(Path(name)) == digest for name, digest in before['input_artifacts'].items()),
                'a protected original input changed')
        require(source_hashes() == report['sources'], 'runner or compiler helper source changed')
        report.update(status='passed', cold_boot_count=4, ordinary_program_executions=6,
                      frozen_package_reproduced_sha256=sha_file(out / 'frozen-after.xpk'),
                      source_disks_preserved=True,
                      final_disks={'newlib': sha_file(old_disk), 'glibc': sha_file(new_disk)},
                      host_tools={'work_disk_host_sha256': sha_file(fat_tool(build=False)),
                                  'xypm_disk_host_sha256': sha_file(xypm_tool())})
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS four cold boots, six ordinary programs, SDK rollback guards and preserved user data')


if __name__ == '__main__':
    main()
