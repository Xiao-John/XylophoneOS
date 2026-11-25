#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify the locked glibc archive with its reviewed release signing key."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / 'src/ports/glibc'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def decode_key(path):
    """Remove OpenPGP ASCII armor; gpgv performs all cryptographic checks."""
    text = Path(path).read_text(encoding='ascii')
    begin = '-----BEGIN PGP PUBLIC KEY BLOCK-----'
    end = '-----END PGP PUBLIC KEY BLOCK-----'
    if text.count(begin) != 1 or text.count(end) != 1:
        raise ValueError('expected one public key armor block')
    before, body = text.split(begin, 1)
    body, after = body.split(end, 1)
    if before.strip() or after.strip():
        raise ValueError('unexpected content outside public key armor')
    body = body.removeprefix('\r\n') if body.startswith('\r\n') else body.removeprefix('\n')
    lines = body.splitlines()
    while lines and lines[0]:
        if ':' not in lines.pop(0):
            raise ValueError('invalid public key armor header')
    if not lines:
        raise ValueError('missing public key armor data')
    lines.pop(0)
    if lines and lines[-1].startswith('='):
        lines.pop()  # Transport CRC is redundant with the pinned SHA-256.
    return base64.b64decode(''.join(lines), validate=True)


def check_status(returncode, output, expected):
    statuses = [line.split()[1:] for line in output.splitlines()
                if line.startswith('[GNUPG:] ')]
    rejected = {'BADSIG', 'ERRSIG', 'EXPSIG', 'EXPKEYSIG', 'REVKEYSIG',
                'NO_PUBKEY', 'KEYEXPIRED', 'SIGEXPIRED', 'KEYREVOKED',
                'NODATA', 'FAILURE', 'ERROR', 'UNEXPECTED', 'BADARMOR'}
    if returncode or any(item and item[0] in rejected for item in statuses):
        raise ValueError('release signature rejected by gpgv')
    valid = [item for item in statuses if item and item[0] == 'VALIDSIG']
    good = [item for item in statuses if item and item[0] == 'GOODSIG']
    if (len(valid) != 1 or len(good) != 1 or len(valid[0]) != 11
            or valid[0][1] != expected['signing_fingerprint']
            or valid[0][10] != expected['primary_fingerprint']
            or valid[0][8] not in ('8', '9', '10', '11')
            or valid[0][9] != '00'):
        raise ValueError('unexpected signer, digest algorithm or signature class')
    return {'signing_fingerprint': valid[0][1],
            'primary_fingerprint': valid[0][10],
            'signature_timestamp': int(valid[0][3]),
            'hash_algorithm': int(valid[0][8])}


def verify_source(archive, output, signature=None, key=None, gpgv='gpgv'):
    archive = Path(archive).resolve(strict=True)
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('verification output must be a new directory')
    lock_path = PORT / 'source_lock.json'
    lock = json.loads(lock_path.read_text())
    trust = lock['signer_trust']
    signature = Path(signature or PORT / trust['signature_file']).resolve(strict=True)
    key = Path(key or PORT / trust['key_file']).resolve(strict=True)
    selected = shutil.which(gpgv)
    if not selected:
        raise ValueError('gpgv is required for source authentication')
    verifier = Path(selected).resolve(strict=True)
    output.mkdir(parents=True)
    report = {'schema': 1, 'status': 'verifying',
              'verified_at': datetime.now(timezone.utc).isoformat(),
              'lock_sha256': digest(lock_path),
              'archive_sha256': digest(archive),
              'signature_sha256': digest(signature), 'key_sha256': digest(key),
              'verifier': {'name': verifier.name, 'sha256': digest(verifier)},
              'trust_record': trust}

    def save():
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    try:
        for field, actual, wanted in (
                ('archive', report['archive_sha256'], lock['archive_sha256']),
                ('signature', report['signature_sha256'], lock['signature_sha256']),
                ('key', report['key_sha256'], trust['key_sha256'])):
            if actual != wanted:
                raise ValueError(field + ' SHA-256 differs from reviewed source lock')
        if archive.stat().st_size != lock['archive_bytes']:
            raise ValueError('archive size differs from source lock')
        keyring = output / 'release_key.gpg'
        keyring.write_bytes(decode_key(key))
        homedir = output / 'gnupg'
        homedir.mkdir(mode=0o700)
        command = [str(verifier), '--homedir', str(homedir), '--keyring',
                   str(keyring), '--status-fd', '1', str(signature), str(archive)]
        env = {name: value for name, value in os.environ.items()
               if name not in ('GNUPGHOME', 'GPG_AGENT_INFO', 'LD_PRELOAD', 'LD_LIBRARY_PATH')}
        env['LC_ALL'] = 'C'
        result = subprocess.run(command, capture_output=True, env=env, timeout=60)
        (output / 'gpgv.status').write_bytes(result.stdout)
        (output / 'gpgv.log').write_bytes(result.stderr)
        report['gpgv_exit'] = result.returncode
        report['signature'] = check_status(result.returncode,
                                            result.stdout.decode('utf-8', errors='replace'), trust)
        for path, expected in ((archive, report['archive_sha256']),
                               (signature, report['signature_sha256']),
                               (key, report['key_sha256']),
                               (lock_path, report['lock_sha256']),
                               (verifier, report['verifier']['sha256'])):
            if digest(path) != expected:
                raise ValueError('verification input changed while checking signature')
        report['status'] = 'upstream_signature_verified'
        report['evidence'] = {name: digest(output / name)
                              for name in ('gpgv.status', 'gpgv.log', 'release_key.gpg')}
        save()
        return report
    except BaseException as error:
        report['status'] = 'rejected'
        report['error'] = str(error)
        save()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--signature', type=Path)
    parser.add_argument('--key', type=Path)
    parser.add_argument('--gpgv', default='gpgv')
    args = parser.parse_args()
    report = verify_source(args.archive, args.output, args.signature, args.key, args.gpgv)
    print(report['status'] + ': ' + report['signature']['signing_fingerprint'])


if __name__ == '__main__':
    main()
