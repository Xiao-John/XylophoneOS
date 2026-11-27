#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Authenticate the GCC shared-runtime inputs against the reviewed GNU keyring."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from verify_glibc_source import check_status, digest, extract_verified_source, read_archive

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'src/ports/gcc/shared_source_auth.json'
SOURCE_LOCK = ROOT / 'src/ports/gcc/source_lock.json'


def read_lock():
    data, source_data = LOCK.read_bytes(), SOURCE_LOCK.read_bytes()
    lock, source = json.loads(data), json.loads(source_data)
    if (lock['schema'] != 1 or lock['component'] != 'gcc'
            or lock['version'] != source['version'] or lock['archive_sha256'] != source['sha256']):
        raise ValueError('GCC shared authentication and source locks disagree')
    return lock, {'authentication_lock_sha256': hashlib.sha256(data).hexdigest(),
                  'source_lock_sha256': hashlib.sha256(source_data).hexdigest()}


def verify_source(archive, signature, keyring, output, *, archive_data=None):
    lock, locks = read_lock()
    archive, signature, keyring = (Path(p).resolve(strict=True) for p in (archive, signature, keyring))
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('verification output must be a new directory')
    verifier_name = shutil.which('gpgv')
    if verifier_name is None:
        raise ValueError('gpgv is required for GCC source authentication')
    verifier = Path(verifier_name).resolve(strict=True)
    if archive_data is None:
        archive_data = read_archive(archive, lock['archive_bytes'])
    if not isinstance(archive_data, bytes):
        raise ValueError('GCC archive snapshot must be immutable bytes')
    with signature.open('rb') as stream:
        signature_data = stream.read(1025)
    with keyring.open('rb') as stream:
        key_data = stream.read(lock['keyring_bytes'] + 1)
    output.mkdir(parents=True, mode=0o700)
    report = {'schema': 1, 'status': 'verifying', 'component': 'gcc', **locks,
              'verified_at': datetime.now(timezone.utc).isoformat(),
              'archive_sha256': hashlib.sha256(archive_data).hexdigest(),
              'signature_sha256': hashlib.sha256(signature_data).hexdigest(),
              'keyring_sha256': hashlib.sha256(key_data).hexdigest(),
              'verifier': {'name': verifier.name, 'sha256': digest(verifier)},
              'primary_fingerprint': lock['primary_fingerprint'],
              'signing_fingerprint': lock['signing_fingerprint'],
              'previous_keyring_sha256': lock['previous_keyring_sha256']}

    def save():
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    try:
        for field in ('archive', 'signature', 'keyring'):
            if report[field + '_sha256'] != lock[field + '_sha256']:
                raise ValueError(field + ' SHA-256 differs from the reviewed GCC authentication lock')
        if len(archive_data) != lock['archive_bytes'] or len(key_data) != lock['keyring_bytes']:
            raise ValueError('GCC source input size differs from the authentication lock')
        home = output / 'gnupg'
        home.mkdir(mode=0o700)
        environment = {key: value for key, value in os.environ.items()
                       if key not in ('GNUPGHOME', 'GPG_AGENT_INFO', 'LD_PRELOAD', 'LD_LIBRARY_PATH')}
        environment['LC_ALL'] = 'C'
        with tempfile.TemporaryDirectory(prefix='source_', dir=output) as temporary:
            files = {}
            for name, body in (('archive', archive_data), ('signature', signature_data), ('keyring', key_data)):
                files[name] = Path(temporary) / name
                files[name].write_bytes(body)
            result = subprocess.run([str(verifier), '--homedir', str(home), '--keyring',
                                     str(files['keyring']), '--status-fd', '1',
                                     str(files['signature']), str(files['archive'])],
                                    capture_output=True, env=environment, timeout=60)
            if any(digest(path) != report[name + '_sha256'] for name, path in files.items()):
                raise ValueError('GCC private verification snapshot changed')
        (output / 'gpgv.status').write_bytes(result.stdout)
        (output / 'gpgv.log').write_bytes(result.stderr)
        report['gpgv_exit'] = result.returncode
        report['signature'] = check_status(result.returncode,
                                            result.stdout.decode('utf-8', errors='replace'), lock)
        for path, expected in ((archive, report['archive_sha256']),
                               (signature, report['signature_sha256']),
                               (keyring, report['keyring_sha256']),
                               (verifier, report['verifier']['sha256']),
                               (LOCK, report['authentication_lock_sha256']),
                               (SOURCE_LOCK, report['source_lock_sha256'])):
            if digest(path) != expected:
                raise ValueError('GCC verification input changed while checking the signature')
        report['status'] = 'upstream_signature_verified'
        report['evidence'] = {name: digest(output / name) for name in ('gpgv.status', 'gpgv.log')}
        save()
        return report
    except BaseException as error:
        report['status'] = 'rejected'
        report['error'] = str(error)
        save()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for flag in ('archive', 'signature', 'keyring', 'output'):
        parser.add_argument('--' + flag, type=Path, required=True)
    args = parser.parse_args()
    report = verify_source(args.archive, args.signature, args.keyring, args.output)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
