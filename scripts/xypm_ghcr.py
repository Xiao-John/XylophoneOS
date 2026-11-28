# SPDX-License-Identifier: Apache-2.0
"""Fetch a digest-pinned public XPK artifact through the host HTTPS stack."""
import hashlib
from http.client import HTTPException
from pathlib import Path
import re
import tempfile
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from xypm_format import MAX_ARCHIVE, MAX_MANIFEST, PackageError, require, strict_json, verify_package

REGISTRY = 'ghcr.io'
MANIFEST = 'application/vnd.oci.image.manifest.v1+json'
XPK = 'application/vnd.xos.xpk.v1'
EMPTY_CONFIG = {
    'mediaType': 'application/vnd.oci.empty.v1+json',
    'digest': 'sha256:' + hashlib.sha256(b'{}').hexdigest(),
    'size': 2,
}
DIGEST = re.compile(r'sha256:[a-f0-9]{64}')
REPOSITORY = re.compile(r'[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_ghcr(path, *, token=None, accept='application/json', blob=False):
    from urllib.error import HTTPError

    opener = build_opener(NoRedirect())
    url = 'https://' + REGISTRY + path
    headers = {'Accept': accept, 'Accept-Encoding': 'identity'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    for _ in range(6):
        try:
            return opener.open(Request(url, headers=headers), timeout=20)
        except HTTPError as error:
            with error:
                require(blob and error.code in (301, 302, 303, 307, 308),
                        f'GHCR returned HTTP {error.code}')
                locations = error.headers.get_all('Location', [])
                require(len(locations) == 1, 'ambiguous GHCR blob redirect')
                url = urljoin(url, locations[0])
                target = urlsplit(url)
                require(target.scheme == 'https' and target.username is None
                        and target.password is None and target.port in (443, None)
                        and not target.fragment and target.hostname == 'pkg-containers.githubusercontent.com',
                        'unapproved GHCR blob redirect')
                headers.pop('Authorization', None)
    require(False, 'too many GHCR blob redirects')


def check_response(response):
    require(response.status == 200, 'expected HTTP 200')
    require(response.headers.get_all('Content-Encoding', []) in ([], ['identity']),
            'unsupported GHCR content encoding')


def read_body(response, limit):
    try:
        return response.read(limit)
    except HTTPException:
        raise PackageError('invalid or incomplete GHCR HTTP body') from None


def read_metadata(response):
    check_response(response)
    data = read_body(response, MAX_MANIFEST + 1)
    require(len(data) <= MAX_MANIFEST, 'GHCR metadata too large')
    return data


def xpk_layer(data):
    manifest = strict_json(data)
    require(isinstance(manifest, dict) and type(manifest.get('schemaVersion')) is int
            and manifest['schemaVersion'] == 2 and manifest.get('mediaType') == MANIFEST
            and manifest.get('artifactType') == XPK, 'expected an OCI XPK manifest')
    config = manifest.get('config')
    require(isinstance(config, dict) and type(config.get('size')) is int
            and all(config.get(key) == value for key, value in EMPTY_CONFIG.items()),
            'expected an empty OCI XPK config descriptor')
    layers = manifest.get('layers')
    require(isinstance(layers, list) and len(layers) == 1 and isinstance(layers[0], dict),
            'expected exactly one XPK layer')
    layer = layers[0]
    digest, size = layer.get('digest'), layer.get('size')
    require(layer.get('mediaType') == XPK and isinstance(digest, str)
            and DIGEST.fullmatch(digest) and type(size) is int
            and 0 < size <= MAX_ARCHIVE and size % 512 == 0, 'invalid XPK descriptor')
    return digest, size


def fetch_package(repository, manifest_digest, output, profile, *, request=open_ghcr):
    require(len(repository) <= 255 and REPOSITORY.fullmatch(repository), 'invalid GHCR repository')
    require(DIGEST.fullmatch(manifest_digest), 'expected an immutable sha256 manifest digest')
    output = Path(output)
    require(not output.exists() and not output.is_symlink(), 'XPK output already exists')
    token_path = '/token?' + urlencode({'service': REGISTRY, 'scope': f'repository:{repository}:pull'})
    with request(token_path) as reply:
        credential = strict_json(read_metadata(reply))
    token = credential.get('token') if isinstance(credential, dict) else None
    require(isinstance(token, str) and 0 < len(token) <= 8192
            and re.fullmatch(r'[A-Za-z0-9._~+/=-]+', token), 'invalid GHCR token')

    with request(f'/v2/{repository}/manifests/{manifest_digest}', token=token, accept=MANIFEST) as reply:
        data = read_metadata(reply)
    require('sha256:' + hashlib.sha256(data).hexdigest() == manifest_digest,
            'GHCR manifest SHA-256 mismatch')
    digest, size = xpk_layer(data)
    with tempfile.TemporaryDirectory(prefix='.xypm-ghcr-', dir=output.parent) as directory:
        staged = Path(directory) / 'package.xpk'
        with request(f'/v2/{repository}/blobs/{digest}', token=token,
                     accept='application/octet-stream', blob=True) as reply, staged.open('xb') as stream:
            check_response(reply)
            remaining = size
            while remaining:
                chunk = read_body(reply, min(remaining, 65536))
                require(chunk, 'truncated GHCR blob')
                stream.write(chunk)
                remaining -= len(chunk)
            require(not read_body(reply, 1), 'GHCR blob exceeds descriptor size')
        result = verify_package(staged, profile, digest[7:])
        # A racing writer cannot replace or be replaced by the verified package.
        output.hardlink_to(staged)
    return {'status': 'downloaded_verified', 'manifest_digest': manifest_digest,
            'sha256': digest[7:], 'size': size, 'package_id': result['manifest']['id']}
