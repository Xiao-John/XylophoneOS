#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the real release-signature gate and corrupted input rejection."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_glibc_source import PORT, verify_source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    archive = args.archive.resolve(strict=True)
    cases = []
    report = verify_source(archive, output / 'valid')
    assert report['status'] == 'upstream_signature_verified'
    cases.append({'name': 'real_gpgv_valid_release', 'status': 'passed'})
    lock = json.loads((PORT / 'source_lock.json').read_text())
    trust = lock['signer_trust']
    inputs = {'archive': archive, 'signature': PORT / trust['signature_file'],
              'key': PORT / trust['key_file']}
    for name, source in inputs.items():
        damaged = output / ('damaged_' + name)
        shutil.copyfile(source, damaged)
        with damaged.open('r+b') as stream:
            byte = stream.read(1)
            stream.seek(0)
            stream.write(bytes([byte[0] ^ 1]))
        kwargs = {name: damaged} if name != 'archive' else {}
        try:
            verify_source(damaged if name == 'archive' else archive,
                          output / ('reject_' + name), **kwargs)
        except ValueError as error:
            assert name + ' SHA-256' in str(error), str(error)
        else:
            raise AssertionError('corrupted ' + name + ' was accepted')
        rejected = json.loads((output / ('reject_' + name) / 'report.json').read_text())
        assert rejected['status'] == 'rejected'
        cases.append({'name': 'reject_corrupted_' + name, 'status': 'passed'})
    def evidence_snapshot():
        return {str(path.relative_to(output / 'valid')): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (output / 'valid').rglob('*') if path.is_file()}
    existing = evidence_snapshot()
    try:
        verify_source(archive, output / 'valid')
    except ValueError as error:
        assert 'new directory' in str(error)
    else:
        raise AssertionError('verification evidence was overwritten')
    assert evidence_snapshot() == existing, 'existing verification evidence changed'
    cases.append({'name': 'preserve_existing_evidence', 'status': 'passed'})
    result = {'status': 'passed', 'cases': cases,
              'scope': 'actual gpgv plus pinned archive/signature/key tampering',
              'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
    (output / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
