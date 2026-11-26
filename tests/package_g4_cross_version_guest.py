# SPDX-License-Identifier: Apache-2.0
"""Verify native P2-to-P3 xypm upgrade, disk profile refusal and cold recovery."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_smoke import Guest
from make_work_disk import create_fat32
from package_p2_faults import sparse_copy
from package_p2_verify_guest import fixtures, quiet_maintenance_guest
from process_smoke import resources
from task_smoke import pump, send_bytes
from xypm_format import canonical, load_json, require, sha_file, verify_package
from xypm_image import Disk, query_image
from xypm_repository import create_repository, make_lock, write_metadata

DB = '/var/lib/xypm/db.json'
INDEX = '/var/lib/xypm/index.tsv'
JOURNAL = '/var/lib/xypm/transaction'
MARKERS = (JOURNAL, '/var/lib/xypm/txdata', '/var/lib/xypm/transaction_commit')
XYPM = '/usr/bin/xypm'
NOTE = '/out/user.txt'
USER_DATA = b'Created by the old guest before xypm upgrade\n'
P2 = b'xypm 0.3 (P2 transactions)'
P3 = b'xypm 0.4.0 (P3 offline repositories)'


def checked_build(receipt, profile):
    result = load_json(receipt)
    package = verify_package(Path(result['package']), profile)
    elf = sha_file(result['elf'])
    file = next(item for item in package['manifest']['files'] if '/' + item['path'] == XYPM)
    require(package['sha256'] == result['sha256'] and file['sha256'] == elf,
            'xypm package, ELF and build receipt disagree')
    require(package['manifest']['id'] == 'xos.xypm', 'unexpected package ID')
    manifest = package['manifest']
    return result | {'elf_sha256': elf, 'upstream_version': manifest['upstream_version'],
                     'revision': manifest['revision']}


def command(guest, line, expected, timeout=180):
    start = len(guest.output)
    send_bytes(guest, line.encode() + b'\r')
    match = guest.expect_any((expected, b'xsh> '), start=start, timeout=timeout)
    require(match == expected, 'unexpected output: ' + repr(guest.output[start:][-2400:]))
    guest.expect_supervisor(start=start, timeout=timeout)
    return bytes(guest.output[start:])


@contextmanager
def boot(image, disk, stage, output, legacy=False):
    guest = Guest(image, stage, work_disk=disk, log_dir=output)
    try:
        guest.expect(b'xos64> ', timeout=60)
        send_bytes(guest, b'run\r')
        guest.expect_supervisor(trace=True, timeout=60)
        pump(guest, 1.0)
        if b'maintenance: persistent recovery required' not in guest.output:
            if legacy:
                start = len(guest.output)
                send_bytes(guest, b'demo quiet\r')
                guest.expect_any((b'demo tasks stopped', b'demo tasks already stopped'), start=start, timeout=45)
                guest.expect_supervisor(start=start, timeout=45)
            else:
                quiet_maintenance_guest(guest)
        yield guest
    finally:
        guest.close()


def readback(disk_path, folder, profile, manager, application_packages):
    files = query_image(disk_path, profile, 'verify-installed')['files']
    with tempfile.TemporaryDirectory(dir=folder) as temporary, Disk(disk_path, temporary, True) as disk:
        files_read = {path: disk.export(path).read_bytes() for path in (DB, INDEX, NOTE)}
        require(all(disk.info(path) is None for path in MARKERS), 'transaction material left after recovery')
        require(sha_file(disk.export(XYPM)) == manager['elf_sha256'], 'installed executable is not the expected binary')
    require(files_read[NOTE] == USER_DATA, 'guest user data changed')
    database = json.loads(files_read[DB])
    index = files_read[INDEX].decode()
    require(database['format_version'] == 1 and database['target_profile'] == profile['id']
            and index.startswith('xypm-index-v1\n'), 'P2 database or index format changed')
    packages = query_image(disk_path, profile)['packages']
    require({row['id']: row['sha256'] for row in packages} == application_packages | {'xos.xypm': manager['sha256']},
            'installed package identity changed')
    dependencies = database['packages']['friends.dependent']['manifest']['runtime_dependencies']
    require(dependencies == [{'id': 'friends.p2', 'upstream_version': '1.0', 'revision': 2147483647,
                              'sha256': application_packages['friends.p2']}], 'installed exact dependency lock changed')
    hashes = {path: hashlib.sha256(data).hexdigest() for path, data in files_read.items()}
    return {'file_sha256': hashes, 'package_rows': packages, 'verified_files': files, 'dependency_lock': dependencies}


def committed(guest, worker, operation, package, package_id, options=''):
    output = command(guest, f'maint-run {worker} {operation} {package}{options}', b'maintenance: completed')
    require(f'{operation} {package_id} committed'.encode() in output, 'package mutation did not commit')
    return output


def run(args, report):
    output = args.output.resolve()
    old_profile = load_json(args.profile)
    glibc_profile = load_json(args.next_profile)
    legacy = old_profile['id'] != glibc_profile['id']
    old = checked_build(args.old, old_profile)
    new = checked_build(args.new, glibc_profile)
    require((old['upstream_version'], old['revision'], new['upstream_version'], new['revision']) ==
            ('0.1.0', 0, '0.4.0', 0), 'cross-version inputs required')
    builds = (old, new)
    if not legacy:
        fault = checked_build(args.fault, glibc_profile)
        builds += (fault,)
    report['mode'] = 'legacy_newlib_profile_refusal' if legacy else 'same_glibc_profile_upgrade'
    report['builds'] = [{key: build[key] for key in ('sha256', 'elf_sha256', 'upstream_version', 'revision',
                                                     'target_profile', 'files')} for build in builds]
    report['profile_sha256'] = {'old': sha_file(args.profile), 'new': sha_file(args.next_profile)}
    images = [args.old_image, args.new_image]
    report['system'] = []
    for image in images:
        manifest = load_json(image.parent / 'manifest.json')
        digest = sha_file(image)
        require(digest == manifest['artifacts'][image.name]['sha256'], 'unbound system image')
        report['system'].append({'build_id': manifest['build_id'], 'image_sha256': digest,
                                 'manifest_sha256': sha_file(image.parent / 'manifest.json')})
    report['qemu'] = subprocess.check_output(['qemu-system-x86_64', '--version'], text=True).splitlines()[0]

    fixture_dir = output / 'fixtures'
    fixture_dir.mkdir()
    fixtures(fixture_dir, old_profile, Path(old['elf']))
    packages = [fixture_dir / name for name in ('valid.xpk', 'dep_good.xpk')]
    application_packages = dict(zip(('friends.p2', 'friends.dependent'), map(sha_file, packages)))
    inputs = {'old': old['elf'], 'old.xpk': old['package'], 'new': new['elf'], 'new.xpk': new['package'],
              'base.xpk': packages[0], 'app.xpk': packages[1]}
    if not legacy:
        inputs['fault'] = fault['elf']
        repo = fixture_dir / 'repo'
        create_repository(packages, repo, glibc_profile)
        write_metadata(repo / 'lock.json', make_lock(repo, [sha_file(packages[1])], glibc_profile))
        inputs.update({'repo/' + path.name: path for path in repo.iterdir()})
        report['repository'] = {'index_sha256': sha_file(repo / 'index.json'), 'lock_sha256': sha_file(repo / 'lock.json')}
    base = output / 'created-by-old.img'
    create_fat32(base, 512)
    with Disk(base, fixture_dir) as disk:
        disk.command('mkdir', '/out')
        if not legacy:
            disk.command('mkdir', '/out/repo')
        for name, source in inputs.items():
            disk.command('import', '/out/' + name, source)
        require(all(disk.info(path) is None for path in (DB, INDEX, XYPM, NOTE)), 'virgin disk already has state')
    report['initial_disk_sha256'] = sha_file(base)
    with boot(args.old_image, base, 'old-created', output, legacy) as guest:
        command(guest, 'exec-file /out/old --version', P2)
        committed(guest, '/out/old', 'install', '/out/old.xpk', 'xos.xypm')
        command(guest, 'exec-file /usr/bin/xypm --version', P2)
        committed(guest, XYPM, 'install', '/out/base.xpk', 'friends.p2')
        committed(guest, XYPM, 'install', '/out/app.xpk', 'friends.dependent')
        if not legacy:
            command(guest, 'exec-file /usr/bin/xypm repo-verify /out/repo /out/repo/lock.json', b'unsupported command')
        start = len(guest.output)
        send_bytes(guest, b'edit /out/user.txt\r')
        guest.expect(b'| ', start=start, timeout=45)
        send_bytes(guest, USER_DATA.rstrip(b'\n') + b'\r:wq\r')
        guest.expect(b'[edit] saved /out/user.txt', start=start, timeout=45)
        guest.expect_supervisor(start=start, timeout=45)
        command(guest, 'sync', b'[files] sync=ok')
    original = readback(base, output, old_profile, old, application_packages)
    report['created_by_old'] = original | {'disk_sha256': sha_file(base)}

    if legacy:
        control = output / 'boot-control.img'
        sparse_copy(base, control)
        with boot(args.new_image, control, 'boot-control', output) as guest:
            command(guest, 'exec-file /out/new --version', P3)
            command(guest, 'sync', b'[files] sync=ok')
        trial = output / 'profile-refusal.img'
        sparse_copy(base, trial)
        with boot(args.new_image, trial, 'profile-refusal', output) as guest:
            command(guest, 'exec-file /out/new --version', P3)
            result = command(guest, 'maint-run /out/new upgrade /out/new.xpk', b'maintenance: retained')
            require(b'installed database profile mismatch' in result, 'expected database profile refusal')
            result = command(guest, 'maint-recover-boot', b'maintenance: completed')
            require(b'xypm-recover: no transaction' in result, 'profile refusal created a transaction')
            command(guest, 'sync', b'[files] sync=ok')
        observed = readback(trial, output, old_profile, old, application_packages)
        require(observed == original, 'refused write changed the old package database or files')
        control_sha, trial_sha = sha_file(control), sha_file(trial)
        report['profile_refusal'] = observed | {'disk_sha256': trial_sha, 'boot_control_sha256': control_sha}
        require(trial_sha == control_sha, 'refused write changed disk beyond ordinary boot activity')
        with boot(args.old_image, trial, 'profile-refusal-old-cold', output, legacy=True) as guest:
            command(guest, 'exec-file /usr/bin/xypm --version', P2)
            command(guest, 'exec-file /usr/bin/xypm list', b'friends.dependent')
            command(guest, 'cat /out/user.txt', USER_DATA.rstrip(b'\n'))
        return

    def cold_read(disk, stage):
        with boot(args.new_image, disk, stage, output) as guest:
            command(guest, 'exec-file /usr/bin/xypm --version', P3)
            command(guest, 'exec-file /usr/bin/xypm list', b'friends.dependent')
            command(guest, 'cat /out/user.txt', USER_DATA.rstrip(b'\n'))
            command(guest, 'exec-file /usr/bin/xypm repo-verify /out/repo /out/repo/lock.json',
                    b'Repository closure verified: 2 packages')
        return readback(disk, output, glibc_profile, new, application_packages) | {'disk_sha256': sha_file(disk)}

    upgraded = output / 'upgraded.img'
    sparse_copy(base, upgraded)
    with boot(args.new_image, upgraded, 'upgrade', output) as guest:
        baseline = resources(guest)
        committed(guest, '/out/new', 'upgrade', '/out/new.xpk', 'xos.xypm', ' --sha256 ' + new['sha256'])
        require(resources(guest) == baseline, 'resource counters changed after upgrade')
    report['upgraded_after_cold_boot'] = cold_read(upgraded, 'upgrade-cold')

    probe = output / 'checkpoint-probe.img'
    sparse_copy(base, probe)
    with boot(args.new_image, probe, 'checkpoint-probe', output) as guest:
        result = committed(guest, '/out/fault', 'upgrade', '/out/new.xpk', 'xos.xypm')
        match = re.search(rb'xypm-test: self_removed=(\d+)', result)
        require(match is not None, 'missing xypm self-removal checkpoint')
        step = int(match.group(1))
    interrupted = output / 'interrupted.img'
    sparse_copy(base, interrupted)
    with boot(args.new_image, interrupted, 'interrupt', output) as guest:
        result = command(guest, f'maint-run /out/fault upgrade /out/new.xpk --fault-after {step}',
                         b'maintenance: retained')
        require(f'xypm-test: injected={step}'.encode() in result, 'fault checkpoint was not reached')
    with Disk(interrupted, fixture_dir, True) as disk:
        require(disk.info(XYPM) is None and disk.info(JOURNAL) is not None, 'missing interrupted transaction state')
    report['interrupted'] = {'checkpoint': step, 'disk_sha256': sha_file(interrupted)}
    recovered = output / 'recovered.img'
    sparse_copy(interrupted, recovered)
    with boot(args.new_image, recovered, 'recover', output) as guest:
        require(b'maintenance: persistent recovery required' in guest.output, 'missing immutable recovery gate')
        result = command(guest, 'maint-recover-boot', b'maintenance: completed')
        require(b'transaction rolled back' in result, 'immutable worker failed to roll back')
        command(guest, 'exec-file /usr/bin/xypm --version', P2)
    restored = readback(recovered, output, glibc_profile, old, application_packages)
    require(restored == original, 'recovery did not restore the original state')
    report['recovered'] = restored | {'disk_sha256': sha_file(recovered)}
    retry = output / 'retry.img'
    sparse_copy(recovered, retry)
    with boot(args.new_image, retry, 'retry', output) as guest:
        committed(guest, '/out/new', 'upgrade', '/out/new.xpk', 'xos.xypm')
    report['retry_after_cold_boot'] = cold_read(retry, 'retry-cold')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ('old', 'new', 'profile', 'next-profile', 'old-image', 'new-image', 'output'):
        parser.add_argument('--' + argument, type=Path, required=True)
    parser.add_argument('--fault', type=Path, help='required for same-profile upgrade')
    args = parser.parse_args()
    if load_json(args.profile)['id'] == load_json(args.next_profile)['id'] and args.fault is None:
        parser.error('--fault is required for a same-profile upgrade')
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'test_sha256': sha_file(__file__)}
    try:
        run(args, report)
        report['status'] = 'passed'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (args.output / 'report.json').write_bytes(canonical(report))


if __name__ == '__main__':
    main()
