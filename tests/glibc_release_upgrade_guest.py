# SPDX-License-Identifier: Apache-2.0
"""Replay a synced xypm upgrade interruption on the actual glibc release disk."""

import argparse
import hashlib
from pathlib import Path
import re
import sys
import tarfile
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from glibc_release_packages_guest import USER_DATA, USER_PATH, boot as boot_release
from glibc_release_packages_guest import command, python_smoke
from package_g4_cross_version_guest import DB, INDEX, JOURNAL, MARKERS, XYPM, boot, checked_build
from package_glibc_release import IMAGES, INSTALLER, MANIFEST, ORDINARY, verify_assembled, verify_disk
from package_p2_faults import resources, sparse_copy
from package_p2_verify_guest import make_archive
from xypm_format import canonical, load_json, require, sha_file, verify_package
from xypm_image import Disk

MARKER = 'usr/share/xos-test/idna-upgrade.txt'
MARKER_DATA = b'IDNA package maintenance revision acceptance\n'
PYTHON_TEST = b'import gzip, idna\nassert gzip.decompress(gzip.compress(b"XOS")) == b"XOS"\nassert idna.encode("buecher.example") == b"buecher.example"\nprint("RELEASE_UPGRADE_PYTHON_OK")\n'
PYTHON_MARKER = b'RELEASE_UPGRADE_PYTHON_OK'


def next_wheel(release_root, expected, profile, output):
    wheel = release_root / 'packages/wheel.xpk'
    manifest = verify_package(wheel, profile, expected_sha256=expected['sha256'])['manifest']
    require(manifest['id'] == 'python_idna', 'the release wheel must contain IDNA')
    with tarfile.open(wheel, 'r:') as archive:
        bodies = {item['path']: archive.extractfile('payload/' + item['path']).read()
                  for item in manifest['files']}
    require(MARKER not in bodies, 'unexpected preexisting fixture path')
    bodies[MARKER] = MARKER_DATA
    manifest['revision'] += 1
    manifest['files'].append({'path': MARKER, 'type': 'file', 'size': len(MARKER_DATA),
                              'sha256': hashlib.sha256(MARKER_DATA).hexdigest(), 'role': 'data'})
    manifest['files'].sort(key=lambda item: item['path'])
    make_archive(output, manifest, bodies)
    digest = verify_package(output, profile)['sha256']
    return expected | {'sha256': digest, 'files': len(manifest['files'])}


def disk_state(disk, temp, profile, packages, release, upgraded):
    summary = verify_disk(disk, profile, packages)
    with Disk(disk, temp, True) as fat:
        require(all(fat.info(name) is None for name in MARKERS), 'persistent transaction state remains')
        require(fat.export(USER_PATH).read_bytes() == USER_DATA, 'user data changed')
        require(sha_file(fat.export(XYPM)) == release['xypm_sha256'], 'release xypm changed')
        require(sha_file(fat.export('/usr/bin/dash')) == release['dash_sha256'], 'release Dash changed')
        if upgraded:
            require(fat.export('/' + MARKER).read_bytes() == MARKER_DATA, 'upgraded payload missing')
        else:
            require(fat.info('/' + MARKER) is None, 'uncommitted upgrade payload remains')
        return {'packages': summary, 'db_sha256': sha_file(fat.export(DB)),
                'index_sha256': sha_file(fat.export(INDEX)), 'user_sha256': sha_file(fat.export(USER_PATH))}


def run(root, fault_receipt, out, work, report):
    release, profile = verify_assembled(root)
    fault = checked_build(fault_receipt, profile)
    packages = release['packages']
    source = root / IMAGES / 'work_disk.img'
    ordinary = root / IMAGES / ORDINARY
    installer = root / IMAGES / INSTALLER
    report.update(release_manifest_sha256=sha_file(root / MANIFEST),
                  profile_sha256=release['application_sdk']['profile_sha256'],
                  installer_iso_sha256=release['installer_iso']['sha256'],
                  ordinary_iso_sha256=release['system']['iso']['sha256'],
                  original_disk_sha256=release['work_disk']['sha256'], fault_elf_sha256=fault['elf_sha256'])
    upgraded_packages = packages | {'wheel': next_wheel(root, packages['wheel'], profile, work / 'next.xpk')}
    report['upgrade_package'] = upgraded_packages['wheel']
    initial = work / 'installed.img'
    sparse_copy(source, initial)
    require(sha_file(initial) == report['original_disk_sha256'], 'release disk copy differs')
    (work / 'release_user.txt').write_bytes(USER_DATA)
    (work / 'upgrade.py').write_bytes(PYTHON_TEST)
    with Disk(initial, work) as fat:
        for name in ('release_user.txt', 'upgrade.py', 'next.xpk'):
            fat.command('import', '/out/' + name, work / name)
        fat.command('import', '/out/upgrade-test.elf', Path(fault['elf']))
    guest = boot_release(installer, initial, out, 'installer', release['system']['build_id'])
    try:
        python_smoke(guest, resources(guest), '/out/upgrade.py', PYTHON_MARKER)
        command(guest, 'sync', b'[files] sync=ok')
    finally:
        guest.close()
    report['installed'] = disk_state(initial, work, profile, packages, release, False)

    trial = work / 'trial.img'
    sparse_copy(initial, trial)
    with boot(ordinary, trial, 'calibrate', out) as guest:
        calibration = command(guest, 'maint-run /out/upgrade-test.elf upgrade /out/next.xpk',
                              b'maintenance: completed', timeout=600)
        require(b'upgrade python_idna committed' in calibration, 'checkpoint calibration did not commit')
        count = re.search(rb'xypm-test: checkpoints=(\d+)', calibration)
        require(count is not None and int(count[1]) > 2, 'no commit phase checkpoints')
        # The final two checkpoints stage and publish the commit record.
        checkpoint = int(count[1]) - 2
    disk_state(trial, work, profile, upgraded_packages, release, True)
    trial.unlink()
    sparse_copy(initial, trial)

    with boot(ordinary, trial, 'interrupt', out) as guest:
        injected = command(guest, f'maint-run /out/upgrade-test.elf upgrade /out/next.xpk --fault-after {checkpoint}',
                           b'maintenance: retained', timeout=600)
        require(f'xypm-test: injected={checkpoint}'.encode() in injected, 'upgrade checkpoint was missed')
    with Disk(trial, work, True) as fat:
        require(fat.info(JOURNAL) is not None and fat.info(MARKERS[-1]) is None,
                'interrupted upgrade did not leave an uncommitted journal')
        require(fat.export('/' + MARKER).read_bytes() == MARKER_DATA, 'interruption preceded package replacement')
    report['interrupted'] = {'checkpoint': checkpoint, 'disk_sha256': sha_file(trial)}

    with boot(ordinary, trial, 'recover', out) as guest:
        require(b'maintenance: persistent recovery required' in guest.output, 'recovery gate did not activate')
        restored = command(guest, 'maint-recover-boot', b'maintenance: completed', timeout=600)
        require(b'transaction rolled back' in restored, 'immutable recovery did not roll back')
    report['recovered'] = disk_state(trial, work, profile, packages, release, False)
    require(report['recovered'] == report['installed'], 'rollback did not restore the baseline exactly')

    with boot(ordinary, trial, 'retry', out) as guest:
        baseline = resources(guest)
        digest = upgraded_packages['wheel']['sha256']
        completed = command(guest, f'maint-run {XYPM} upgrade /out/next.xpk --sha256 {digest}',
                            b'maintenance: completed', timeout=600)
        require(b'upgrade python_idna committed' in completed and resources(guest) == baseline,
                'release xypm retry failed or left guest resources')
    with boot(ordinary, trial, 'retry-cold', out) as guest:
        python_smoke(guest, resources(guest), '/out/upgrade.py', PYTHON_MARKER)
    report['after_cold_boot'] = disk_state(trial, work, profile, upgraded_packages, release, True)
    require(sha_file(source) == report['original_disk_sha256'], 'release input disk was changed')
    report['status'] = 'passed_subset'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ('release', 'fault-build', 'output'):
        parser.add_argument('--' + argument, type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True)
    report = {'status': 'failed', 'runner_sha256': sha_file(Path(__file__)),
              'not_run': ['physical_power_loss', 'sector_tearing']}
    try:
        with TemporaryDirectory(dir=out) as temp:
            run(args.release.resolve(), args.fault_build.resolve(), out, Path(temp), report)
    except (Exception, SystemExit) as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_bytes(canonical(report))
    print('PASS native glibc release upgrade, rollback, and cold retry')


if __name__ == '__main__':
    main()
