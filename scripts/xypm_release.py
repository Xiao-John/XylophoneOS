#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Sign an exact repository closure with an independently provisioned key.

This publisher tool grants no guest authority. The native verifier uses a
compiled bootstrap, the protected broker checkpoint, and the kernel clock.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from xypm_format import HEX, canonical, fields, identifier, load_json, require, sha_file
from xypm_repository import verify_repository

DOMAIN = b'XOS-XYPM-RELEASE-V1\x00'
RELEASE_LIMIT = 4096
INTEGER_LIMIT = (1 << 63) - 1
ED25519_SPKI = bytes.fromhex('302a300506032b6570032100')


def integer(value, name, minimum=1, maximum=INTEGER_LIMIT):
    require(type(value) is int and minimum <= value <= maximum, 'invalid ' + name)
    return value


def trust_config(value):
    fields(value, ('format_version', 'repository_id', 'target_profile', 'key_epoch',
                   'minimum_sequence', 'maximum_validity_seconds', 'public_key_ed25519'))
    integer(value['format_version'], 'bootstrap format', maximum=1)
    identifier(value['repository_id'])
    identifier(value['target_profile'])
    integer(value['key_epoch'], 'bootstrap key epoch')
    integer(value['minimum_sequence'], 'bootstrap sequence floor')
    integer(value['maximum_validity_seconds'], 'bootstrap validity limit', maximum=31 * 86400)
    key = value['public_key_ed25519']
    require(type(key) is str and HEX.fullmatch(key) and int(key, 16), 'invalid bootstrap Ed25519 key')
    return value


def trust_header(value):
    trust = trust_config(value)
    return ('// SPDX-License-Identifier: Apache-2.0\n#pragma once\n'
            '#include "xypm_repository_auth.hpp"\n'
            'inline constexpr xypm_repository_auth::bootstrap xypm_bootstrap = {'
            + json.dumps(trust['repository_id']) + ',' + json.dumps(trust['target_profile']) + ','
            + ','.join(str(trust[name]) + 'ULL' for name in
                       ('key_epoch', 'minimum_sequence', 'maximum_validity_seconds'))
            + ',{' + ','.join(str(byte) for byte in bytes.fromhex(trust['public_key_ed25519']))
            + '}};\n')


def validate_release(value, trust):
    trust_config(trust)
    fields(value, ('format_version', 'repository_id', 'target_profile', 'key_epoch', 'sequence',
                   'issued_at', 'expires_at', 'index_sha256', 'lock_sha256', 'generation_id',
                   'generation_sha256'))
    integer(value['format_version'], 'release format', maximum=1)
    for name in ('repository_id', 'target_profile', 'key_epoch'):
        require(value[name] == trust[name] and type(value[name]) is type(trust[name]),
                'release differs from bootstrap: ' + name)
    integer(value['sequence'], 'release sequence', minimum=trust['minimum_sequence'])
    for name in ('issued_at', 'expires_at', 'generation_id'):
        integer(value[name], name)
    require(0 < value['expires_at'] - value['issued_at'] <= trust['maximum_validity_seconds'],
            'repository validity interval rejected')
    for name in ('index_sha256', 'lock_sha256', 'generation_sha256'):
        require(type(value[name]) is str and HEX.fullmatch(value[name]), 'invalid ' + name)
    return value


def sign(repository, lock, generation, trust, private_key, sequence, issued_at, expires_at, output,
         profile=None):
    trust_config(trust)
    result = verify_repository(repository, lock, profile)
    require(result['target_profile'] == trust['target_profile'], 'bootstrap/repository profile mismatch')
    body = Path(generation).read_bytes()
    require(128 <= len(body) <= 6272, 'invalid generation manifest length')
    magic, version, size, generation_id = struct.unpack_from('<QIIQ', body)
    require(magic == 0x314e4547534f5858 and version == 1 and size == len(body),
            'invalid generation manifest header')
    release = validate_release({
        'format_version': 1, 'repository_id': trust['repository_id'],
        'target_profile': trust['target_profile'], 'key_epoch': trust['key_epoch'],
        'sequence': sequence, 'issued_at': issued_at, 'expires_at': expires_at,
        'index_sha256': result['index_sha256'], 'lock_sha256': result['lock_sha256'],
        'generation_id': generation_id, 'generation_sha256': hashlib.sha256(body).hexdigest(),
    }, trust)
    metadata = canonical(release)
    require(len(metadata) <= RELEASE_LIMIT, 'release exceeds 4096 bytes')
    public = subprocess.check_output(['openssl', 'pkey', '-in', str(private_key),
                                      '-pubout', '-outform', 'DER'], stderr=subprocess.PIPE)
    require(public == ED25519_SPKI + bytes.fromhex(trust['public_key_ed25519']),
            'signing key differs from independent bootstrap')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='xypm_sign_', dir=output) as temporary:
        message = Path(temporary) / 'message'
        signature = Path(temporary) / 'signature'
        message.write_bytes(DOMAIN + metadata)
        subprocess.run(['openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(private_key),
                        '-in', str(message), '-out', str(signature)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        signed = signature.read_bytes()
        require(len(signed) == 64, 'unexpected Ed25519 signature size')
        (output / 'release.json').write_bytes(metadata)
        (output / 'release.sig').write_bytes(signed)
    return {'repository_id': trust['repository_id'], 'key_epoch': trust['key_epoch'],
            'sequence': sequence, 'metadata_sha256': sha_file(output / 'release.json'),
            'signature_sha256': sha_file(output / 'release.sig'),
            'bootstrap_sha256': hashlib.sha256(canonical(trust)).hexdigest(),
            'generation_sha256': release['generation_sha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repository', 'lock', 'generation', 'trust', 'private-key', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--profile', type=Path)
    for name in ('sequence', 'issued-at', 'expires-at'):
        parser.add_argument('--' + name, type=int, required=True)
    args = parser.parse_args()
    result = sign(args.repository, args.lock, args.generation, load_json(args.trust),
                  args.private_key, args.sequence, args.issued_at, args.expires_at,
                  args.output, load_json(args.profile) if args.profile else None)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
