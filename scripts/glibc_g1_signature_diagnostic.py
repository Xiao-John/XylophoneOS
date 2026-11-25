#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the pinned candidate with gpgv; keyring provenance remains external."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

ARCHIVE_SHA = '37f600f2bef3c5e8300147059568b2a2e40a7ad6ccc65ce942556d49429cc667'
SIGNATURE_SHA = '44aabe605a02a56959bab51b92d985945db66dbd0117debe3d741252b2133ec6'
SIGNER = 'FD19E6D31B192EE4DC63EAD3DC2B16215ED5412A'
PRIMARY = '35B17DF5752577CA0C541CEB94BFDF4484AD142F'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--signature', type=Path, required=True)
    p.add_argument('--keyring', type=Path, required=True, help='binary keyring; establish its provenance separately')
    p.add_argument('--gpgv', default='gpgv')
    args = p.parse_args()
    if digest(args.archive) != ARCHIVE_SHA or digest(args.signature) != SIGNATURE_SHA:
        raise SystemExit('candidate archive or signature hash mismatch')
    result = subprocess.run([args.gpgv, '--keyring', str(args.keyring.resolve()), '--status-fd', '1',
                             str(args.signature), str(args.archive)], capture_output=True, text=True)
    statuses = [line.split()[1:] for line in result.stdout.splitlines() if line.startswith('[GNUPG:] ')]
    valid = [s for s in statuses if s and s[0] == 'VALIDSIG']
    rejected = {'BADSIG', 'ERRSIG', 'EXPSIG', 'EXPKEYSIG', 'REVKEYSIG', 'NO_PUBKEY'}
    failure = result.returncode != 0 or any(s and s[0] in rejected for s in statuses)
    failure |= len(valid) != 1 or valid[0][1] != SIGNER or valid[0][-1] != PRIMARY
    failure |= not any(s and s[0] == 'GOODSIG' for s in statuses)
    print(f'keyring_sha256={digest(args.keyring)}')
    print(f'gpgv_exit={result.returncode}; result={"REJECTED" if failure else "SIGNATURE_VALID"}')
    print('Keyring provenance and trust require independent verification; not a release authorization.')
    if failure:
        sys.stderr.write(result.stderr)
        sys.stderr.write(result.stdout)
    return int(failure)


if __name__ == '__main__':
    sys.exit(main())
