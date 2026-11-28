#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Repeat an accepted R1 distribution in fresh, independently bound receivers.

This is a consumer qualification workflow, not a release uploader. It rebuilds
the accepted native system from its recorded source, relinks all 17 distributed
glibc programs, checks the corresponding source materials, runs their actual
guest substitutions, and freezes only after every required stage succeeds.
"""

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from xypm_format import canonical, load_json, require, sha_file

LOCK = ROOT / 'config/release/p1_j_r1_repeat.json'
RECEIVERS = {
    'xypm': ('xypm-relink.tar.gz', 'xypm_relink_manifest_sha256'),
    'dash': ('dash-relink.tar.gz', 'dash_relink_manifest_sha256'),
    'daily': ('daily-relink.tar.gz', 'daily_relink_manifest_sha256'),
    'make': ('gnu-make-relink.tar.gz', 'gnu_make_relink_manifest_sha256'),
    'cpython': ('cpython-relink.tar.gz', 'cpython_relink_manifest_sha256'),
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def file_record(path):
    return {'bytes': path.stat().st_size, 'sha256': sha_file(path)}


def checked_file(path, expected):
    require(path.is_file() and not path.is_symlink(), 'missing regular input: ' + path.name)
    require(file_record(path) == expected, 'input identity differs: ' + path.name)
    return path


def safe_extract(archive, destination, *, strip=None):
    """Reject duplicate names, links, traversal and special files before extraction."""
    require(not destination.exists(), 'extraction destination already exists')
    destination.mkdir(parents=True)
    with tarfile.open(archive, 'r:*') as source:
        entries = source.getmembers()
        seen = set()
        names = []
        total = 0
        for entry in entries:
            path = PurePosixPath(entry.name)
            require(not path.is_absolute() and '..' not in path.parts and '\\' not in entry.name,
                    'unsafe archive path')
            require(entry.name not in seen and (entry.isfile() or entry.isdir()),
                    'duplicate or nonregular archive member')
            seen.add(entry.name)
            if strip:
                require(path.parts and path.parts[0] == strip, 'archive root differs')
                path = PurePosixPath(*path.parts[1:])
            require(path.as_posix() not in ('', '.') or entry.isdir(), 'empty file name')
            total += entry.size
            require(total <= 4 * 1024 ** 3 and len(entries) <= 100000,
                    'archive extraction exceeds limits')
            names.append((entry, path))
        for entry, relative in names:
            target = destination / relative
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(entry) as incoming, target.open('xb') as output:
                    shutil.copyfileobj(incoming, output)
                target.chmod(entry.mode & 0o777)


def verify_checksums(root, name, expected_count):
    records = {}
    for line in (root / name).read_text().splitlines():
        digest, separator, filename = line.partition('  ')
        path = PurePosixPath(filename)
        require(separator and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest),
                'invalid checksum entry')
        require(path.name == filename and filename not in ('', '.', '..') and filename not in records,
                'invalid or duplicate checksum filename')
        require(sha_file(root / filename) == digest, 'bundle checksum differs: ' + filename)
        records[filename] = digest
    require(len(records) == expected_count, 'checksum inventory differs')
    return records


def entry_gate(lock):
    """The first qualification and delivery are required, never inferred from this run."""
    result = {}
    for name in ('first_qualification', 'delivery_receipt'):
        item = lock[name]
        path = checked_file(ROOT / item['path'], item['artifact'])
        result[name] = load_json(path)
    first, delivery = result['first_qualification'], result['delivery_receipt']
    require(first['status'] == lock['first_qualification_status'], 'first R1 qualification is not accepted')
    require(delivery['r1']['public_download_verified'] is True,
            'first R1 public delivery has not passed')
    selected = [asset for asset in delivery['r1']['assets'] if asset['name'] == lock['bundle_name']]
    require(len(selected) == 1 and selected[0]['sha256'] == lock['bundle']['sha256']
            and selected[0]['bytes'] == lock['bundle']['bytes'], 'first delivery binding differs')
    return {name: lock[name]['artifact'] for name in result}


def clean_snapshot(revision, archive, destination, *, include_gate=False):
    paths = ['Makefile', 'VERSION', 'LICENSE', 'NOTICE', 'licenses', 'src', 'scripts', 'tests', 'config',
             'docs/releases']
    if include_gate:
        lock = load_json(LOCK)
        paths += [lock[name]['path'] for name in ('first_qualification', 'delivery_receipt')]
    with archive.open('xb') as output:
        subprocess.run(['git', 'archive', '--format=tar', revision, *paths], cwd=ROOT,
                       stdout=output, check=True)
    safe_extract(archive, destination)


class Workflow:
    def __init__(self, args, lock):
        self.args = args
        self.lock = lock
        self.output = args.output.absolute()
        require(not self.output.exists() and not self.output.is_symlink(), 'choose a new run directory')
        self.output.mkdir(parents=True, exist_ok=False)
        self.report = {'format': 'xos_r1_repeat_v1', 'status': 'running',
                       'run_id': uuid.uuid4().hex, 'started_at_utc': utc_now(),
                       'output_was_absent': True, 'published': False, 'steps': []}
        self.save()

    def save(self):
        (self.output / 'run.json').write_bytes(canonical(self.report))

    def command(self, name, argv, *, cwd=None):
        log = self.output / (name + '.log')
        step = {'name': name, 'started_at_utc': utc_now(), 'status': 'running', 'log': log.name}
        self.report['steps'].append(step)
        self.save()
        print('R1_REPEAT ' + name, flush=True)
        with log.open('xb') as stream:
            result = subprocess.run(list(map(str, argv)), cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
        step.update(returncode=result.returncode, finished_at_utc=utc_now(),
                    status='passed' if result.returncode == 0 else 'failed',
                    log_sha256=sha_file(log))
        self.save()
        require(result.returncode == 0, 'stage failed: ' + name)

    def sdk(self, name, mount, *command):
        self.command(name, [self.args.sdk_launcher, '--workdir', mount,
                            '/usr/bin/env', 'XOS_QMP_TRANSPORT=pipe', 'PYTHONDONTWRITEBYTECODE=1',
                            *command])

    def inside(self, stage):
        self.sdk(stage, self.output, 'python3', '/work/runner/scripts/repeat_glibc_distribution.py',
                 '_inside', '--root', '/work', '--stage', stage)

    def run(self):
        gate = entry_gate(self.lock)
        checked_file(self.args.bundle, self.lock['bundle'])
        checked_file(self.args.frozen_sdk, self.lock['frozen_sdk']['artifact'])
        require(not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'],
                                            cwd=ROOT), 'commit the runner source before qualification')
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        launcher = self.args.sdk_launcher.resolve(strict=True)
        require(launcher.is_file(), 'SDK launcher is not a regular file')
        self.report.update(entry_gate=gate, bundle=self.lock['bundle'],
                           frozen_sdk_archive=self.lock['frozen_sdk']['artifact'],
                           runner_commit=revision, runner_sha256=sha_file(Path(__file__)),
                           lock_sha256=sha_file(LOCK), sdk_launcher_sha256=sha_file(launcher),
                           system_source_commit=self.lock['system_source_commit'])
        self.save()
        clean_snapshot(revision, self.output / 'runner.tar', self.output / 'runner', include_gate=True)
        clean_snapshot(self.lock['system_source_commit'], self.output / 'system_source.tar',
                       self.output / 'system_source')
        self.report['source_archives'] = {name: file_record(self.output / name)
                                          for name in ('runner.tar', 'system_source.tar')}
        safe_extract(self.args.bundle, self.output / 'bundle', strip=self.lock['bundle_root'])
        bundle = self.output / 'bundle'
        self.report['outer_checksums'] = verify_checksums(bundle, 'BUNDLE-CHECKSUMS.sha256', 22)
        self.report['frozen_checksums'] = verify_checksums(bundle, 'CHECKSUMS.sha256', 19)
        safe_extract(self.args.frozen_sdk, self.output / 'frozen_sdk')
        self.inside('prepare')
        self.sdk('system_build', self.output / 'system_source', 'python3',
                 'scripts/build.py', '--quiet-demos-on-launch')
        self.inside('verify_system')
        supplements = load_json(bundle / 'distribution_manifest.json')
        for name, (archive, manifest_key) in RECEIVERS.items():
            root = self.output / 'receivers' / name
            root.mkdir(parents=True)
            shutil.copyfile(bundle / archive, root / archive)
            receiver = 'glibc_release_' + name + '_relink_receiver.sh'
            shutil.copyfile(self.output / 'runner/tests' / receiver, root / 'receiver.sh')
            self.sdk('receiver_' + name, root, 'bash', '/work/receiver.sh', '/work/' + archive,
                     supplements['supplements'][archive]['sha256'], supplements[manifest_key], '/work/result')
        self.inside('verify_receivers')
        self.inside('source_materials')
        self.inside('combined_guest')
        self.inside('relink_guests')
        self.inside('negative_gates')
        self.inside('freeze')
        qualification = load_json(self.output / 'qualification.json')
        require(qualification['status'] == 'passed', 'qualification did not pass')
        self.report.update(status='passed', finished_at_utc=utc_now(),
                           qualification=qualification,
                           qualification_sha256=sha_file(self.output / 'qualification.json'))
        # A mutation during a long guest run must invalidate the result.
        checked_file(self.args.bundle, self.lock['bundle'])
        checked_file(self.args.frozen_sdk, self.lock['frozen_sdk']['artifact'])
        require(sha_file(launcher) == self.report['sdk_launcher_sha256'], 'SDK launcher changed')
        self.save()


def inside_prepare(root):
    from package_glibc_release import release_checksums, verify_assembled
    from xos_sdk import setup
    bundle = root / 'bundle'
    release = load_json(bundle / 'release_manifest.json')
    destination = root / 'release'
    destination.mkdir()
    for name in (*release['archives'], 'release_manifest.json', 'system_manifest.json'):
        shutil.copyfile(bundle / name, destination / name)
    (destination / 'CHECKSUMS.sha256').write_bytes(release_checksums(destination, release))
    for name in ('application-sdk', 'images', 'packages'):
        safe_extract(destination / (name + '.tar.gz'), destination / name, strip=name)
    verify_assembled(destination)
    frozen = root / 'frozen_sdk/xylophoneos_revival_0.0.1-1024_sdk'
    setup(root / 'sdk_state.json', destination / 'application-sdk', frozen)
    system = load_json(bundle / 'system_manifest.json')
    source = root / 'system_source'
    actual = {name: sha_file(source / name) for name in system['sources']}
    require(actual == system['sources'], 'recorded system source differs from clean checkout')
    (root / 'source_binding.json').write_bytes(canonical({
        'status': 'passed', 'sources': actual, 'source_files': len(actual),
        'system_source_commit': load_json(LOCK)['system_source_commit']}))


def inside_verify_system(root):
    recorded = load_json(root / 'bundle/system_manifest.json')
    actual = load_json(root / 'system_source/build/manifest.json')
    require(actual['sources'] == recorded['sources'] and actual['source_sha256'] == recorded['source_sha256']
            and actual['build_id'] == recorded['build_id'], 'rebuilt source identity differs')
    # Manifest paths differ between independent receivers; executable bytes must not.
    matched = {}
    for name in ('xos-install.iso', 'kernel.bin', 'user_hello.image.elf'):
        value = file_record(root / 'system_source/build' / name)
        require(value == recorded['artifacts'][name], 'rebuilt artifact differs: ' + name)
        matched[name] = value
    require(actual['tools'] == recorded['tools'], 'rebuilt tool versions differ')
    require(actual['kernel_layout'] == recorded['kernel_layout'] and actual['symbols'] == recorded['symbols'],
            'kernel layout or exported symbols differ')
    (root / 'system_rebuild.json').write_bytes(canonical({'status': 'passed', 'artifacts': matched,
        'build_id': actual['build_id'], 'source_sha256': actual['source_sha256'], 'tools': actual['tools'],
        'debug_elf': {'artifact': file_record(root / 'system_source/build/kernel.elf'),
            'original_sha256': recorded['artifacts']['kernel.elf']['sha256'],
            'comparison': 'debug_paths_differ_between_producer_and_receiver',
            'loadable_binary_layout_and_symbols_identical': True}}))


def inside_verify_receivers(root):
    from xypm_format import verify_package
    release = load_json(root / 'release/release_manifest.json')
    seed = load_json(root / 'release/images/gnu_seed_receipt.json')
    profile = load_json(root / 'release/application-sdk/profile.json')
    expected = {'xypm': release['xypm_sha256'], 'dash': release['dash_sha256'],
                'make': seed['installed_files']['/usr/bin/gmake']}
    python = verify_package(root / 'release/packages/cpython.xpk', profile)['manifest']
    expected['cpython'] = next(item['sha256'] for item in python['files'] if item['role'] == 'executable')
    daily = verify_package(root / 'release/packages/daily.xpk', profile)['manifest']
    results = {}
    for name in RECEIVERS:
        receiver = root / 'receivers' / name
        result = receiver / 'result'
        if name == 'daily':
            want = {Path(item['path']).name: item['sha256'] for item in daily['files']
                    if item['role'] == 'executable'}
            original = {key: sha_file(result / 'original' / key) for key in want}
            replacement = {key: sha_file(result / 'replacement' / key) for key in want}
            require(original == want and all(replacement[key] != want[key] for key in want),
                    'daily receiver program identities differ')
        else:
            original = sha_file(result / 'original.elf')
            replacement = sha_file(result / 'replacement.elf')
            require(original == expected[name] and replacement != original,
                    'receiver program identity differs: ' + name)
        results[name] = {'original': original, 'replacement': replacement,
                         'receiver_sha256': sha_file(receiver / 'receiver.sh')}
    (root / 'receivers.json').write_bytes(canonical({'status': 'passed', 'programs': 17,
        'receivers': results, 'checkout_mounted_in_receivers': False}))


def inside_sources(root):
    from package_glibc_release_sources import verify
    from stage_glibc_release_supplements import stage_glibc_source
    bundle = root / 'bundle'
    supplements = load_json(bundle / 'distribution_manifest.json')
    output = io.StringIO()
    with redirect_stdout(output):
        verify(argparse.Namespace(archive=bundle / 'component-sources.tar.gz',
            manifest=bundle / 'component-sources.json',
            manifest_sha256=supplements['supplements']['component-sources.json']['sha256']))
    staging = root / 'source_verification'
    staging.mkdir()
    glibc = stage_glibc_source(bundle / 'application-sdk.tar.gz', bundle / 'glibc-2.44.tar.xz', staging,
                              load_json(bundle / 'release_manifest.json')['application_sdk']['sdk_manifest_sha256'])
    require(glibc == supplements['glibc_source'], 'authenticated source binding differs')
    (root / 'source_materials.json').write_bytes(canonical({'status': 'passed',
        'components': json.loads(output.getvalue()), 'glibc': glibc}))


def inside_command(root, name, argv):
    with (root / (name + '.log')).open('xb') as stream:
        subprocess.run(list(map(str, argv)), stdout=stream, stderr=subprocess.STDOUT, check=True)


def retire_guest_disk(root, relative, report_name, expected_sha256, consumer_name):
    """Retire closed temporary media only after its last synchronous consumer."""
    report_path, consumer_path = root / report_name, root / consumer_name
    producer, consumer = load_json(report_path), load_json(consumer_path)
    require(producer['status'] == 'passed_subset'
            and consumer['status'] in ('passed', 'passed_subset'),
            'guest media consumer did not complete successfully')
    path = root / relative
    require(path.is_file() and not path.is_symlink(), 'temporary guest media is not a regular file')
    media = file_record(path)
    require(media['sha256'] == expected_sha256, 'completed guest media changed before retirement')
    receipt_path = root / 'guest_disk_retirement.json'
    receipt = load_json(receipt_path) if receipt_path.exists() else {
        'format': 'xos_r1_repeat_guest_media_retirement_v1', 'records': []}
    require(all(item['path'] != relative for item in receipt['records']),
            'guest media already has a retirement record')
    item = {'path': relative, 'artifact': media,
            'producer_report': {'path': report_name, **file_record(report_path)},
            'last_consumer_report': {'path': consumer_name, **file_record(consumer_path)},
            'status': 'verified_before_removal'}
    receipt['records'].append(item)
    receipt_path.write_bytes(canonical(receipt))
    # The synchronous guest/consumer has returned and closed QEMU before this
    # call. Never unlink its input earlier merely because a progress marker exists.
    path.unlink()
    item['status'] = 'removed_after_complete_hash_verification'
    receipt_path.write_bytes(canonical(receipt))


def inside_combined(root):
    inside_command(root, 'combined_guest_detail', [sys.executable, ROOT / 'scripts/release_smoke.py',
                    '--glibc-release', root / 'release', '--output', root / 'combined_guest'])
    seed = load_json(root / 'combined_guest/gnu_seed/report.json')
    retire_guest_disk(root, 'combined_guest/gnu_seed/work_disk.img',
                      'combined_guest/gnu_seed/report.json', seed['final_disk_sha256'],
                      'combined_guest/combined_report.json')
    inside_command(root, 'receiver_preflight', [sys.executable,
                    ROOT / 'tests/glibc_gnu_seed_release_preflight.py', '--release', root / 'release',
                    '--guest-dir', root / 'combined_guest', '--output', root / 'preflight'])
    package = load_json(root / 'combined_guest/report.json')
    retire_guest_disk(root, 'combined_guest/work.img', 'combined_guest/report.json',
                      package['final_disk_sha256'], 'preflight')


def inside_relink_guests(root):
    # These existing guest harnesses place their QEMU/serial logs under the
    # runner's build directory, separate from the rebuilt system tree.
    (ROOT / 'build').mkdir(exist_ok=True)
    release = root / 'release'
    digest = sha_file(release / 'release_manifest.json')
    output = root / 'relink_guests'
    output.mkdir()
    commands = {}
    for name in ('make', 'cpython'):
        result = root / 'receivers' / name / 'result'
        command = [sys.executable, ROOT / ('tests/glibc_release_' + name + '_relink.py'),
            '--release', release, '--release-sha256', digest, '--original', result / 'original.elf',
            '--replacement', result / 'replacement.elf', '--replacement-sha256', sha_file(result / 'replacement.elf'),
            '--output', output / name]
        if name == 'make':
            command += ['--dash', root / 'receivers/dash/result/original.elf']
        commands[name] = command
    daily = root / 'receivers/daily/result'
    commands['daily'] = [sys.executable, ROOT / 'tests/glibc_release_daily_relink.py', '--release', release,
        '--release-sha256', digest, '--relink', daily,
        '--replacement-sha256', sha_file(daily / 'replacement.json'), '--output', output / 'daily']
    dash = root / 'receivers/dash/result'
    # The original manifest is immutable; the separately rebuilt executable was
    # byte-checked above. Use that manifest for the existing R1 receiver gate.
    system = root / 'guest_system'
    system.mkdir()
    shutil.copyfile(root / 'bundle/system_manifest.json', system / 'manifest.json')
    shutil.copyfile(root / 'system_source/build/user_hello.image.elf', system / 'user_hello.image.elf')
    commands['dash'] = [sys.executable, ROOT / 'tests/glibc_release_dash_relink.py', '--release', release,
        '--release-sha256', digest, '--system', system, '--original', dash / 'original.elf',
        '--replacement', dash / 'replacement.elf', '--replacement-sha256', sha_file(dash / 'replacement.elf'),
        '--output', output / 'dash']
    xypm = root / 'receivers/xypm/result'
    disk = root / 'combined_guest/after_installer.img'
    commands['xypm'] = [sys.executable, ROOT / 'tests/glibc_release_xypm_relink.py', 'guest',
        '--release', release, '--original', xypm / 'original.elf', '--replacement', xypm / 'replacement.elf',
        '--installed-disk', disk, '--installed-disk-sha256', sha_file(disk), '--output', output / 'xypm']
    for name, command in commands.items():
        inside_command(root, 'guest_' + name, command)
    reports = {name: load_json(output / name / 'report.json') for name in commands}
    require(all(value['status'] == 'passed_subset' for value in reports.values()), 'a guest did not pass')
    retire_guest_disk(root, 'combined_guest/after_installer.img', 'combined_guest/report.json',
                      reports['xypm']['installed_disk_sha256'], 'relink_guests/xypm/report.json')
    (root / 'relink_guests.json').write_bytes(canonical({'status': 'passed', 'reports': reports}))


def inside_negatives(root):
    from xos_sdk import checked_binding, load_state
    from package_glibc_release_sources import verify
    cases = {}
    def denied(name, function):
        try:
            function()
        except (ValueError, OSError) as error:
            cases[name] = {'status': 'rejected', 'error': str(error).replace(str(root), '${RUN}')}
        else:
            raise ValueError('negative input was accepted: ' + name)
        require(not (root / 'frozen').exists(), 'rejection occurred after publication')
    denied('wrong_bundle_hash', lambda: checked_file(root / 'bundle/glibc-2.44.tar.xz',
        {'bytes': (root / 'bundle/glibc-2.44.tar.xz').stat().st_size, 'sha256': '0' * 64}))
    state = load_state(root / 'sdk_state.json')
    state['bindings']['glibc']['sdk_manifest_sha256'] = '0' * 64
    denied('stale_sdk', lambda: checked_binding(state, 'glibc'))
    denied('missing_source', lambda: verify(argparse.Namespace(archive=root / 'absent_source.tar.gz',
        manifest=root / 'bundle/component-sources.json',
        manifest_sha256=sha_file(root / 'bundle/component-sources.json'))))
    (root / 'negative_gates.json').write_bytes(canonical({'status': 'passed', 'cases': cases,
                                                        'publication_absent_after_each_rejection': True}))


def inside_freeze(root):
    from glibc_release_pipeline import checksum_bytes, freeze
    from package_application_preview import artifact
    bundle = root / 'bundle'
    manifest = load_json(bundle / 'distribution_manifest.json')
    supplements = root / 'supplements'
    supplements.mkdir()
    for name in (*manifest['supplements'], 'distribution_manifest.json'):
        shutil.copyfile(bundle / name, supplements / name)
    records = {**manifest['base_assets'], **manifest['supplements'],
               'distribution_manifest.json': artifact(supplements / 'distribution_manifest.json')}
    (supplements / 'CHECKSUMS.sha256').write_bytes(checksum_bytes(records))
    for name in ('system_rebuild.json', 'receivers.json', 'source_materials.json',
                 'relink_guests.json', 'negative_gates.json'):
        require(load_json(root / name)['status'] == 'passed', 'required qualification is not passed: ' + name)
    retirements = load_json(root / 'guest_disk_retirement.json')
    require({item['path'] for item in retirements['records']} == {
                'combined_guest/gnu_seed/work_disk.img', 'combined_guest/work.img',
                'combined_guest/after_installer.img'}
            and len(retirements['records']) == 3
            and all(item['status'] == 'removed_after_complete_hash_verification'
                    and not (root / item['path']).exists() for item in retirements['records']),
            'closed guest media retirement is incomplete')
    for item in retirements['records']:
        for key in ('producer_report', 'last_consumer_report'):
            proof = item[key]
            checked_file(root / proof['path'], {name: proof[name] for name in ('bytes', 'sha256')})
    freeze(argparse.Namespace(release=root / 'release', supplements=supplements,
                              smoke=root / 'combined_guest', sdk_state=root / 'sdk_state.json',
                              output=root / 'frozen'))
    receipt = load_json(root / 'frozen/pipeline_receipt.json')
    expected = load_json(bundle / 'pipeline_receipt.json')
    require(receipt['sdk_bindings'] == expected['sdk_bindings'], 'frozen SDK identities differ')
    require(all(receipt['assets'][name] == value for name, value in expected['assets'].items()
                if name not in ('package_smoke_report.json', 'gnu_seed_smoke_report.json', 'combined_smoke_report.json')),
            'an immutable distribution input changed')
    result = {'status': 'passed', 'scope': 'accepted_r1_clean_system_and_receiver_reproduction',
              'release_manifest_sha256': receipt['release_manifest_sha256'],
              'sdk_bindings': receipt['sdk_bindings'],
              'system_rebuild': load_json(root / 'system_rebuild.json'),
              'receivers': load_json(root / 'receivers.json'),
              'source_materials': load_json(root / 'source_materials.json'),
              'negative_gates': load_json(root / 'negative_gates.json'),
              'temporary_media_retirements': retirements,
              'guest_reports': load_json(root / 'relink_guests.json'),
              'combined_guest': load_json(root / 'combined_guest/combined_report.json'),
              'frozen_assets': {p.name: file_record(p) for p in (root / 'frozen').iterdir()},
              'not_requalified': ['full_source_recompilation_of_glibc_gcc_and_all_upstream_applications',
                                  'physical_power_loss', 'new_installed_dynamic_network_profile'],
              'published': False}
    (root / 'qualification.json').write_bytes(canonical(result))


INSIDE = {'prepare': inside_prepare, 'verify_system': inside_verify_system,
          'verify_receivers': inside_verify_receivers, 'source_materials': inside_sources,
          'combined_guest': inside_combined, 'relink_guests': inside_relink_guests,
          'negative_gates': inside_negatives, 'freeze': inside_freeze}


def read_run_report(path):
    """Read the completed report envelope, separately from XPK wire metadata."""
    with Path(path).open('rb') as stream:
        data = stream.read(1024 * 1024 + 1)
    require(len(data) <= 1024 * 1024, 'run report exceeds 1 MiB')

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate run-report JSON key')
            result[key] = value
        return result

    def invalid_number(_):
        raise ValueError('non-integer run-report JSON number')

    def walk(value, depth=0):
        require(depth <= 16, 'run-report JSON nesting exceeds 16')
        if isinstance(value, dict):
            for key, item in value.items():
                key.encode('utf-8', 'strict')
                walk(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                walk(item, depth + 1)
        elif isinstance(value, str):
            value.encode('utf-8', 'strict')

    try:
        result = json.loads(data.decode('utf-8', 'strict'), object_pairs_hook=pairs,
                            parse_float=invalid_number, parse_constant=invalid_number)
        walk(result)
    except (UnicodeError, RecursionError, ValueError) as error:
        raise ValueError('invalid run-report JSON: ' + str(error)) from error
    require(type(result) is dict and result.get('format') == 'xos_r1_repeat_v1',
            'unexpected run-report format')
    return result


def compare(paths, output):
    require(len(paths) >= 2, 'at least two independent runs are required')
    runs = [read_run_report(path / 'run.json') for path in paths]
    require(len({item['run_id'] for item in runs}) == len(runs), 'duplicate run identity')
    require(len({path.resolve() for path in paths}) == len(paths), 'duplicate run directory')
    first = runs[0]
    inventories = []
    variable_assets = {'package_smoke_report.json', 'gnu_seed_smoke_report.json',
                       'combined_smoke_report.json', 'pipeline_receipt.json', 'CHECKSUMS.sha256'}
    for path, run in zip(paths, runs):
        require(run['status'] == 'passed' and run['output_was_absent'], 'a run did not pass cleanly')
        require(sha_file(path / 'qualification.json') == run['qualification_sha256']
                and load_json(path / 'qualification.json') == run['qualification'],
                'qualification report changed after its run')
        assets = run['qualification']['frozen_assets']
        require({item.name for item in (path / 'frozen').iterdir()} == set(assets),
                'frozen directory inventory differs after its run')
        require(set(assets) == set(first['qualification']['frozen_assets']),
                'independent frozen inventory differs')
        require(all((path / 'frozen' / name).is_file() and not (path / 'frozen' / name).is_symlink()
                    and file_record(path / 'frozen' / name) == value
                    for name, value in assets.items()),
                'frozen result changed after its run')
        require(all(value == first['qualification']['frozen_assets'][name]
                    for name, value in assets.items() if name not in variable_assets),
                'independent immutable frozen asset differs')
        require(set(run['source_archives']) == {'runner.tar', 'system_source.tar'},
                'source archive inventory differs')
        for name, expected in run['source_archives'].items():
            checked_file(path / name, expected)
        inventories.append({'run_id': run['run_id'], 'files': assets,
            'canonical_inventory_sha256': hashlib.sha256(canonical(assets)).hexdigest(),
            'encoding': 'canonical JSON of original qualification.frozen_assets',
            'exact_inventory_and_every_file_verified': True})
        for key in ('bundle', 'runner_commit', 'runner_sha256', 'lock_sha256', 'sdk_launcher_sha256',
                    'system_source_commit', 'source_archives', 'entry_gate', 'frozen_sdk_archive'):
            require(run[key] == first[key], 'independent run input differs: ' + key)
        for key in ('release_manifest_sha256', 'sdk_bindings', 'system_rebuild', 'receivers'):
            require(run['qualification'][key] == first['qualification'][key], 'reproduced output differs: ' + key)
    result = {'status': 'passed', 'independent_runs': len(runs), 'run_ids': [run['run_id'] for run in runs],
              'programs_per_run': 17, 'system_source_commit': first['system_source_commit'],
              'runner_commit': first['runner_commit'], 'bundle': first['bundle'],
              'sdk_bindings': first['qualification']['sdk_bindings'],
              'system_rebuild': first['qualification']['system_rebuild'],
              'run_reports': [file_record(path / 'run.json') for path in paths],
              'frozen_inventories': inventories,
              'immutable_frozen_files_compared': len(set(first['qualification']['frozen_assets']) - variable_assets),
              'verifier': {'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                    cwd=ROOT, text=True).strip(), 'script_sha256': sha_file(Path(__file__)),
                    'scope': 'read_only_comparison_of_completed_runs'},
              'published': False}
    require(not output.exists(), 'comparison output already exists')
    output.write_bytes(canonical(result))
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='operation', required=True)
    run = sub.add_parser('run', allow_abbrev=False)
    for name in ('bundle', 'frozen-sdk', 'sdk-launcher', 'output'):
        run.add_argument('--' + name, type=Path, required=True)
    inside = sub.add_parser('_inside', allow_abbrev=False)
    inside.add_argument('--root', type=Path, required=True)
    inside.add_argument('--stage', choices=INSIDE, required=True)
    comparison = sub.add_parser('compare', allow_abbrev=False)
    comparison.add_argument('--runs', type=Path, nargs='+', required=True)
    comparison.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    workflow = None
    try:
        if args.operation == '_inside':
            INSIDE[args.stage](args.root)
        elif args.operation == 'compare':
            compare(args.runs, args.output)
        else:
            workflow = Workflow(args, load_json(LOCK))
            workflow.run()
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        if workflow:
            workflow.report.update(status='failed', error=str(error), finished_at_utc=utc_now())
            workflow.save()
        print('repeat glibc distribution: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
