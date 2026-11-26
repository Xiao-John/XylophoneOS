# SPDX-License-Identifier: Apache-2.0
"""Exercise glibc default selection and frozen newlib recovery on separate real disks."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from glibc_newlib_frozen_rollback_guest import FROZEN_PROFILE, executable, guest_run, readback, seed_disk
from make_work_disk import create_fat32
from package_p2_faults import sparse_copy
from shell_launch_support import bind_system
from xypm_format import canonical, load_json, require, sha_file

SOURCE = ROOT / 'docs/reports/glibc_stock_apps_20261126'
USER_DATA = b'glibc-user-data\n'
NO_PROFILE = 'work disk has no xypm profile'


def run(args, report):
    out = args.output.resolve()
    state = out / 'selection.json'
    kit = out / 'configured-kit'
    shutil.copytree(args.kit, kit, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    defaults = [sys.executable, str(ROOT / 'scripts/xos_sdk.py'), '--state', str(state)]

    def command(*arguments, reject=None):
        result = subprocess.run([*defaults, *map(str, arguments)], cwd=ROOT, text=True, capture_output=True)
        if reject is not None:
            require(result.returncode != 0 and reject in result.stderr,
                    f'expected {reject!r} for {arguments[0]}: {result.stderr}')
            return None
        require(result.returncode == 0, f'{arguments[0]} failed: {result.stderr}')
        return result.stdout

    historical = load_json(args.frozen_report)
    frozen_record = historical['frozen']
    report['previous_frozen_report_sha256'] = sha_file(args.frozen_report)
    original_disk_hash = sha_file(args.frozen_disk)
    require(original_disk_hash == frozen_record['disk_after_rollback_sha256']
            and sha_file(args.original_unmarked) == frozen_record['published_disk_sha256']
            and sha_file(args.frozen_boot) == frozen_record['boot_sha256']
            and sha_file(FROZEN_PROFILE) == frozen_record['profile_sha256']
            and sha_file(args.frozen_package) == frozen_record['application']['package_sha256'],
            'frozen rollback inputs differ from the historical receipts')
    old_disk = out / 'frozen-work.img'
    unmarked = out / 'unmarked-release-copy.img'
    sparse_copy(args.frozen_disk, old_disk)
    sparse_copy(args.original_unmarked, unmarked)
    old_project = out / 'old-project'
    shutil.copytree(args.frozen_project, old_project, ignore=shutil.ignore_patterns('build', '__pycache__'))
    scratch = out / 'readback'
    old_user = readback(old_disk, '/state/user.txt', scratch)
    initial_old_app = sha_file(old_project / 'xos_app.json')

    command('setup', '--glibc-kit', kit, '--newlib-sdk', args.newlib_sdk)
    selected = load_json(state)
    require(selected['active'] == 'glibc', 'initial default is not glibc')
    report['bindings'] = {key: {name: value for name, value in binding.items() if name != 'root'}
                          for key, binding in selected['bindings'].items()}
    state_initial = sha_file(state)
    command('setup', '--glibc-kit', kit, '--newlib-sdk', args.newlib_sdk, reject='File exists')
    require(sha_file(state) == state_initial, 'repeated setup replaced the configured selection')

    packages, receipt = {}, {}
    for language in ('c', 'cpp'):
        name = 'selection.kit_' + language
        project = out / ('new-' + language)
        command('app', 'init', project, '--language', language, '--id', name)
        require(load_json(project / 'xos_app.json')['target_profile'] == selected['bindings']['glibc']['profile_id'],
                'new application missed the configured default')
        shutil.copyfile(SOURCE / ('external.' + language), project / 'src' / ('main.' + language))
        command('app', 'build', project)
        command('app', 'check', project)
        package = out / (language + '.xpk')
        command('app', 'pack', project, '--output', package)
        command('xypm', 'verify', package)
        packages[language] = package
        receipt[language] = executable(package, kit / 'profile.json', '/usr/bin/kit_' + language,
                                       binding=selected['bindings']['glibc'])
    report['glibc_packages'] = receipt

    command('app', 'build', old_project, reject='project target_profile mismatch')
    command('xypm', 'verify', args.frozen_package, reject='package target profile mismatch')
    command('xypm', 'verify', args.frozen_package, '--prof', FROZEN_PROFILE, reject='supplies its own')
    command('xypm', 'verify-installed', '--image', old_disk, reject='database profile mismatch')
    command('xypm', 'list', '--image', unmarked, reject=NO_PROFILE)
    command('xypm', 'install', packages['c'], '--offline', '--image', unmarked,
            '--output-image', out / 'refused-unmarked.img', reject=NO_PROFILE)
    repository = out / 'repository'
    lock = out / 'lock.json'
    command('xypm', 'repo-create', packages['c'], '--output', repository)
    command('xypm', 'repo-lock', repository, sha_file(packages['c']), '--output', lock)
    command('xypm', 'repo-install', repository, lock, 'selection.kit_c', '--offline', '--image', unmarked,
            '--output-image', out / 'refused-repository.img', reject=NO_PROFILE)
    require(sha_file(unmarked) == frozen_record['published_disk_sha256']
            and all(not (out / name).exists() for name in ('refused-unmarked.img', 'refused-repository.img')),
            'initialized-profile guard changed the old unmarked disk or published a candidate')
    report['unmarked_disk_rejections'] = ['list', 'install', 'repo-install']

    blank = out / 'new-blank.img'
    initial = out / 'new-c.img'
    new_disk = out / 'glibc-work.img'
    create_fat32(blank, 512)
    subprocess.run([sys.executable, str(ROOT / 'scripts/xypm.py'), 'install', str(packages['c']), '--offline',
                    '--profile', str(kit / 'profile.json'), '--image', str(blank), '--output-image', str(initial)],
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    command('xypm', 'install', packages['cpp'], '--offline', '--image', initial, '--output-image', new_disk)
    command('xypm', 'verify-installed', '--image', new_disk)
    seed_disk(new_disk, scratch, USER_DATA)
    system = args.system.resolve()
    manifest = bind_system(system)
    image = system / 'xos-install.iso'
    report['glibc_system_manifest_sha256'] = sha_file(system / 'manifest.json')
    report['glibc_iso_sha256'] = sha_file(image)
    new_commands = [('exec-file /usr/bin/kit_c', b'GLIBC_KIT_C_OK 2.44'),
                    ('exec-file /usr/bin/kit_cpp', b'GLIBC_KIT_CPP_OK vector thread exception')]
    report['guests']['glibc_before'] = guest_run(out, image, new_disk, 'glibc_before',
                                                manifest['build_id'], new_commands)
    disk_hash = sha_file(new_disk)
    report['glibc_disk_before_switch_sha256'] = disk_hash

    unavailable = out / 'kit-unavailable'
    kit.rename(unavailable)
    try:
        command('status', reject='SDK must be a real directory')
        require(load_json(state)['active'] == 'glibc', 'failed active kit silently changed runtime')
        command('use', 'newlib')
        rolled_back = sha_file(state)
        command('use', 'glibc', reject='SDK must be a real directory')
        require(load_json(state)['active'] == 'newlib' and sha_file(state) == rolled_back,
                'failed selection failed to preserve the frozen rollback')
        require(sha_file(old_disk) == original_disk_hash and sha_file(new_disk) == disk_hash,
                'SDK selection wrote to a working disk')
        command('xypm', 'verify', packages['c'], reject='package target profile mismatch')
        command('xypm', 'verify-installed', '--image', new_disk, reject='database profile mismatch')
        command('app', 'build', old_project)
        command('app', 'check', old_project)
        repack = out / 'frozen-repack.xpk'
        command('app', 'pack', old_project, '--output', repack)
        require(sha_file(repack) == sha_file(args.frozen_package), 'frozen XPK did not reproduce')
        command('xypm', 'verify-installed', '--image', old_disk)
        require(sha_file(old_project / 'xos_app.json') == initial_old_app, 'rollback retargeted the old project')
        report['guests']['frozen_newlib'] = guest_run(out, args.frozen_boot, old_disk, 'frozen_newlib',
            historical['guests']['after']['build_id'],
            [('exec-file /usr/bin/frozen selection', b'FROZEN_RUNTIME_OK selection')], historical=True)
        require(readback(old_disk, '/state/user.txt', scratch) == old_user + b'selection\n',
                'rollback did not read and preserve existing user data')
        old_user_hash = sha_file(scratch)
        command('xypm', 'verify-installed', '--image', old_disk)
    finally:
        unavailable.rename(kit)

    old_after = sha_file(old_disk)
    command('use', 'glibc')
    require(sha_file(state) == state_initial and sha_file(old_disk) == old_after
            and sha_file(new_disk) == disk_hash, 'restoring the default changed bindings or disks')
    report['guests']['glibc_after'] = guest_run(out, image, new_disk, 'glibc_after', manifest['build_id'], new_commands)
    command('xypm', 'verify-installed', '--image', new_disk)
    require(sha_file(args.frozen_disk) == original_disk_hash
            and readback(new_disk, '/state/user.txt', scratch) == USER_DATA,
            'new or original legacy data changed')
    report.update(frozen_boot_sha256=sha_file(args.frozen_boot),
                  original_frozen_disk_sha256=original_disk_hash, unmarked_release_disk_sha256=sha_file(unmarked),
                  glibc_disk_sha256=sha_file(new_disk), frozen_work_disk_sha256=old_after,
                  data_sha256={'glibc': sha_file(scratch), 'frozen': old_user_hash},
                  reproduced_frozen_xpk_sha256=sha_file(repack), status='passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('kit', 'system', 'newlib-sdk', 'frozen-report', 'frozen-disk', 'original-unmarked',
                 'frozen-boot', 'frozen-package', 'frozen-project', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'guests': {}, 'test_sha256': sha_file(__file__),
              'tool_sha256': sha_file(ROOT / 'scripts/xos_sdk.py'),
              'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                                       cwd=ROOT, text=True).strip(),
              'qemu_version': subprocess.check_output(['qemu-system-x86_64', '--version'],
                                                      text=True).splitlines()[0]}
    try:
        run(args, report)
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (args.output / 'report.json').write_bytes(canonical(report))


if __name__ == '__main__':
    main()
