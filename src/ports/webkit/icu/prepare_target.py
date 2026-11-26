#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify the locked ICU4C input and prepare its XOS source tree."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_signature(archive, signature, keys, lock):
    with tempfile.TemporaryDirectory(prefix='icu-keyring-') as temporary:
        keyring = Path(temporary) / 'keys.gpg'
        blocks = re.findall(r'-----BEGIN PGP PUBLIC KEY BLOCK-----\n.*?-----END PGP PUBLIC KEY BLOCK-----',
                            keys.read_text(), re.S)
        packets = []
        for block in blocks:
            body = block.split('\n\n', 1)[1].split('-----END ', 1)[0]
            packets.append(base64.b64decode(''.join(line for line in body.splitlines()
                                                    if line and not line.startswith('=')), validate=True))
        keyring.write_bytes(b''.join(packets))
        checked = subprocess.run(['gpgv', '--homedir', temporary, '--keyring', str(keyring),
                                  '--status-fd', '1', '--', str(signature), str(archive)],
                                 capture_output=True, check=True, text=True)
    valid = [line.split()[2] for line in checked.stdout.splitlines() if line.startswith('[GNUPG:] VALIDSIG ')]
    if valid != [lock['signing_fingerprint']]:
        raise ValueError('unexpected ICU release signature')


def insert_line(path, marker, replacement):
    text = path.read_text()
    matches = [line for line in text.splitlines(keepends=True) if marker in line]
    if len(matches) != 1:
        raise ValueError(f'unexpected upstream ICU source at {path.name}')
    line, = matches
    path.write_text(text.replace(line, replacement(line), 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for parameter in ('archive', 'signature', 'keys', 'output'):
        parser.add_argument('--' + parameter, type=Path, required=True)
    args = parser.parse_args()
    lock = json.loads(Path(__file__).with_name('source_lock.json').read_text())
    if args.archive.stat().st_size != lock['archive_bytes']:
        parser.error('ICU source size differs from lock')
    # Signature validation and extraction must consume the same input bytes.
    with tempfile.TemporaryDirectory(prefix='icu-input-') as temporary:
        archive, signature, keys = (Path(temporary) / name for name in ('source', 'signature', 'keys'))
        inputs = ((args.archive, archive, 'archive_sha256'), (args.signature, signature, 'signature_sha256'),
                  (args.keys, keys, 'keys_sha256'))
        for original, snapshot, field in inputs:
            shutil.copyfile(original, snapshot)
            if sha256(snapshot) != lock[field]:
                parser.error(f'ICU input differs from lock: {field}')
        verify_signature(archive, signature, keys, lock)
        args.output.mkdir(parents=True, exist_ok=False)
        with tarfile.open(archive) as source_archive:
            source_archive.extractall(args.output, filter='data')
    source = args.output / lock['archive_root'] / 'source'
    insert_line(source / 'config.sub', '| haiku* ', lambda line: line + line.replace('haiku', 'xos'))
    insert_line(source / 'configure', 'icu_cv_host_frag=mh-linux ;;',
                lambda line: '*-*-xos*) icu_cv_host_frag=mh-xos ;;\n' + line)
    # ICU uses this upstream fragment as the GNU ELF starting point for new
    # targets. The XOS build recipe enables only the static archive rules.
    fragment = (source / 'config/mh-linux').read_text().replace('Linux-specific setup', 'XOS static ELF build setup')
    (source / 'config/mh-xos').write_text(fragment)


if __name__ == '__main__':
    main()
