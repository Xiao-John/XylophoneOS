# SPDX-License-Identifier: Apache-2.0
"""Replay the actual GNU Seed release archives and reject malformed archive inventories."""
import argparse
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from build_gnu_make import PORT, verify_source
from package_glibc_gnu_seed import MATERIALS_DIR, SOURCE_ARCHIVE
from package_glibc_release import MANIFEST, verify_archive_members, verify_assembled
from xypm_format import canonical, load_json, require, sha_file


def malformed_archives(reference, work):
    member = 'images/gnu_seed_receipt.json'
    receipt = (reference / member).read_bytes()
    expected = {member: {'sha256': sha_file(reference / member), 'bytes': len(receipt)}}
    checks = {}
    for name, entries, message in (
        ('missing', (), 'inventory is incomplete'),
        ('duplicate', ((member, receipt), (member, receipt)), 'duplicate release archive member'),
        ('mismatched_bytes', ((member, receipt[::-1]),), 'release archive entry differs'),
        ('foreign_member', ((member, receipt), ('images/extra.json', b'{}')), 'unexpected release archive member'),
    ):
        path = work / (name + '.tar.gz')
        with tarfile.open(path, 'x:gz') as archive:
            for filename, data in entries:
                entry = tarfile.TarInfo(filename)
                entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
        try:
            verify_archive_members(path, expected)
        except ValueError as error:
            require(message in str(error), 'wrong archive rejection: ' + name)
            checks[name] = str(error)
        else:
            raise ValueError('archive should have been rejected: ' + name)
    return checks


def reopen(release_dir, release, work):
    remote = work / 'receiver'
    remote.mkdir()
    initial = {}
    for name in (*release['archives'], 'CHECKSUMS.sha256', MANIFEST, 'system_manifest.json'):
        source = release_dir / name
        initial[name] = sha_file(source)
        shutil.copyfile(source, remote / name)
    for name in release['archives']:
        if name != SOURCE_ARCHIVE:
            with tarfile.open(remote / name, 'r:gz') as archive:
                archive.extractall(remote, filter='data')
    result, _ = verify_assembled(remote)
    require(result == release, 'reopened recipient assets do not match assembled release')
    selected = {}
    lock = load_json(PORT / 'source_lock.json')
    source_name = 'make-' + lock['version'] + '.tar.gz'
    with tarfile.open(remote / SOURCE_ARCHIVE, 'r:gz') as archive:
        for name in (source_name, source_name + '.sig', 'gnu-keyring.gpg'):
            path = work / name
            with archive.extractfile(MATERIALS_DIR + '/make/' + name) as source, path.open('xb') as dest:
                shutil.copyfileobj(source, dest)
            selected[name] = path
    verify_source(lock, selected[source_name], selected[source_name + '.sig'], selected['gnu-keyring.gpg'],
                  work / 'signature.log')
    require(all(sha_file(release_dir / name) == digest for name, digest in initial.items()),
            'recipient replay wrote an assembly input')
    return {'assets': initial, 'source_signer': lock['signer_primary_fingerprint']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    release, _ = verify_assembled(args.release)
    require('gnu_seed' in release, 'test requires a release carrying GNU Seed')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.gnu_release_check_', dir=args.output.parent) as directory:
        work = Path(directory)
        failures = malformed_archives(args.release, work)
        output = work / 'unselected'
        command = (sys.executable, ROOT / 'scripts/package_release.py', '--release-dir', output,
                   '--gnu-seed-donor', work)
        result = subprocess.run(command, capture_output=True, text=True)
        require(result.returncode == 2 and 'requires --glibc-candidate and all of' in result.stderr
                and not output.exists(), 'unselected GNU release arguments were applied')
        recipient = reopen(args.release, release, work)
    report = {'status': 'passed', 'release_sha256': sha_file(args.release / MANIFEST),
              'recipient': recipient, 'initial_disk_sha256': release['work_disk']['sha256'],
              'archive_negative_cases': failures, 'incomplete_seed_arguments_rejected': True}
    with args.output.open('xb') as stream:
        stream.write(canonical(report))


if __name__ == '__main__':
    main()
