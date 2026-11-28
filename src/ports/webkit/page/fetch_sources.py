#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fetch the already-locked WebCore prerequisites without changing their locks."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import file_digest
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[4]


def digest(path):
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    sources = []
    for name in ('webkit', 'qt6', 'webkit/libxml2', 'webkit/fontconfig', 'webkit/webp', 'zlib', 'lwip'):
        lock_path = ROOT / 'src/ports' / name / 'source_lock.json'
        lock = json.loads(lock_path.read_bytes())
        url = next(lock[key] for key in ('source', 'url', 'archive_url') if key in lock)
        filename = lock.get('archive', url.rsplit('/', 1)[1])
        sources.append((filename, url, lock['sha256'], lock_path))
    lock_path = ROOT / 'src/ports/cpython/sqlite/sqlite_lock.json'
    lock = json.loads(lock_path.read_bytes())
    sources.append((lock['archive'], lock['source'], lock['sha256'], lock_path))
    lock_path = ROOT / 'src/ports/openssl/source_lock.json'
    lock = json.loads(lock_path.read_bytes())
    for url_key, hash_key in (('archive_url', 'archive_sha256'), ('signature_url', 'signature_sha256'),
                              ('release_keys_url', 'release_keys_sha256')):
        sources.append((lock[url_key].rsplit('/', 1)[1], lock[url_key], lock[hash_key], lock_path))
    lock_path = ROOT / 'src/ports/webkit/icu/source_lock.json'
    lock = json.loads(lock_path.read_bytes())
    base = lock['upstream'] + '/releases/download/release-' + lock['version'] + '/'
    for filename, field in ((lock['archive'], 'archive_sha256'), (lock['archive'] + '.asc', 'signature_sha256')):
        sources.append((filename, base + filename, lock[field], lock_path))
    sources.append(('KEYS', 'https://raw.githubusercontent.com/unicode-org/icu/' + lock['keys_revision'] + '/KEYS',
                    lock['keys_sha256'], lock_path))

    def fetch(item):
        filename, url, expected, lock_path = item
        path = out / filename
        if not path.exists():
            temporary = out / (filename + '.part')
            with urllib.request.urlopen(url, timeout=120) as response, temporary.open('wb') as stream:
                while data := response.read(1024 * 1024): stream.write(data)
            if digest(temporary) != expected:
                raise ValueError('download differs from source lock: ' + filename)
            temporary.rename(path)
        if digest(path) != expected:
            raise ValueError('existing archive differs from source lock: ' + filename)
        return filename, {'url': url, 'sha256': expected, 'bytes': path.stat().st_size,
                          'source_lock': str(lock_path.relative_to(ROOT)), 'source_lock_sha256': digest(lock_path)}

    with ThreadPoolExecutor(max_workers=3) as pool:
        files = dict(pool.map(fetch, sources))
    (out / 'receipt.json').write_text(json.dumps({'status': 'locked_downloads_verified', 'files': files}, indent=2) + '\n')


if __name__ == '__main__': main()
