#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""A changed download path cannot replace authenticated extraction bytes."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_glibc_source import PORT, extract_verified_source, read_archive, verify_source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    lock = json.loads((PORT / 'source_lock.json').read_text())
    with tempfile.TemporaryDirectory(prefix='xos_source_snapshot_') as temporary:
        root = Path(temporary)
        download = root / 'download.tar.xz'
        shutil.copyfile(args.archive, download)
        data = read_archive(download, lock['archive_bytes'])
        verification = verify_source(download, output / 'verification', archive_data=data)
        download.write_bytes(b'changed after signature verification\n')
        destination = root / 'extracted'
        destination.mkdir()
        extract_verified_source(data, verification, destination)
        # Compare every regular member, including configure scripts, with the
        # signed snapshot while the original path contains unrelated bytes.
        files = 0
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    wanted = hashlib.sha256(archive.extractfile(member).read()).hexdigest()
                    actual = hashlib.sha256((destination / member.name).read_bytes()).hexdigest()
                    if wanted != actual:
                        raise AssertionError('snapshot member differs: ' + member.name)
                    files += 1
        for name, bad_data, bad_report in (
                ('replaced_download', download.read_bytes(), verification),
                ('mutable_buffer', bytearray(data), verification),
                ('unverified_report', data, {'status': 'rejected'})):
            rejected = root / name
            rejected.mkdir()
            try:
                extract_verified_source(bad_data, bad_report, rejected)
            except ValueError:
                if list(rejected.iterdir()):
                    raise AssertionError('rejected extraction wrote files')
            else:
                raise AssertionError('invalid extraction accepted: ' + name)
    report = {'status': 'passed', 'regular_members_checked': files,
              'checks': ['download_replaced_after_verification', 'every_extracted_regular_member_matches',
                         'replaced_download_rejected', 'mutable_buffer_rejected', 'unverified_report_rejected'],
              'archive_sha256': lock['archive_sha256']}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
