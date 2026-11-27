#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compile an explicitly pinned PEM CA source into a bounded XOS trust snapshot.

This tool never fetches or selects trust automatically. The operator supplies an
independently selected source digest; output metadata is provenance, not a grant
to trust a file loaded from an untrusted path.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
from urllib.parse import urlsplit

MAX_SOURCE = 2 * 1024 * 1024
MAX_SNAPSHOT = 1024 * 1024
MAX_ANCHORS = 256
MAX_CERTIFICATE = 16384
PEM = re.compile(rb'-----BEGIN CERTIFICATE-----\s+([A-Za-z0-9+/=\r\n]+)-----END CERTIFICATE-----')


def compile_snapshot(source, generation, *, openssl='openssl'):
    if not 0 < len(source) <= MAX_SOURCE or type(generation) is not int or not 0 < generation < 2**64:
        raise ValueError('invalid trust source size or generation')
    matches = list(PEM.finditer(source))
    if not 1 <= len(matches) <= MAX_ANCHORS:
        raise ValueError('trust store requires 1..256 CA certificates')
    remainder = PEM.sub(b'', source)
    if b'-----BEGIN' in remainder or b'-----END' in remainder:
        raise ValueError('unrecognized or malformed PEM block')
    anchors = {}
    for match in matches:
        der = base64.b64decode(re.sub(rb'\s+', b'', match[1]), validate=True)
        if not 0 < len(der) <= MAX_CERTIFICATE:
            raise ValueError('certificate exceeds the DER budget')
        digest = hashlib.sha256(der).hexdigest()
        if digest in anchors:
            raise ValueError('duplicate trust anchor')
        checked = subprocess.run([openssl, 'x509', '-inform', 'DER', '-noout',
                                  '-ext', 'basicConstraints,keyUsage'], input=der,
                                 capture_output=True, env={**os.environ, 'LC_ALL': 'C'})
        if checked.returncode or b'CA:TRUE' not in checked.stdout or (
                b'X509v3 Key Usage:' in checked.stdout and b'Certificate Sign' not in checked.stdout):
            raise ValueError('each trust anchor must be a parsed CA with certificate-signing usage')
        canonical = subprocess.run([openssl, 'x509', '-inform', 'DER', '-outform', 'DER'],
                                   input=der, capture_output=True)
        if canonical.returncode or canonical.stdout != der:
            raise ValueError('each anchor must contain exactly one canonical DER certificate')
        anchors[digest] = der
    ordered = sorted(anchors)
    data = struct.pack('<8sIIQQ', b'XOSTRUST', 1, len(ordered), generation, 0)
    data += b''.join(struct.pack('<I', len(anchors[key])) + anchors[key] for key in ordered)
    if len(data) > MAX_SNAPSHOT:
        raise ValueError('trust snapshot exceeds the total budget')
    return data, ordered


def publish_snapshot(destination, data):
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.xos_trust_', dir=destination.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # An exclusive hard link publishes one complete file without replacing
        # another generation, including a destination created during staging.
        os.link(temporary, destination)
    finally:
        os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--pem', type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--source-url', required=True)
    parser.add_argument('--generation', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if not re.fullmatch('[0-9a-f]{64}', args.source_sha256):
            raise ValueError('source SHA-256 must be 64 lowercase hex digits')
        source_url = urlsplit(args.source_url)
        if source_url.scheme != 'https' or not source_url.netloc or source_url.username or source_url.password:
            raise ValueError('use an HTTPS provenance URL without credentials')
        with args.pem.open('rb') as stream:
            source = stream.read(MAX_SOURCE + 1)
        if hashlib.sha256(source).hexdigest() != args.source_sha256:
            raise ValueError('CA source differs from the independently selected digest')
        data, anchors = compile_snapshot(source, args.generation)
        receipt = {'format': 'xos_tls_trust_snapshot_v1', 'generation': args.generation,
                   'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
                   'source_url': args.source_url, 'source_sha256': args.source_sha256,
                   'anchor_sha256': anchors,
                   'selection': 'pin must be supplied by trusted application/deployment configuration'}
        publish_snapshot(args.output, data)
        print(json.dumps(receipt, indent=2))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, 'trust store: ' + str(error) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
