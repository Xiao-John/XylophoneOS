#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prepare the locked WPE WebKit source for the XOS software WebCore target."""

import argparse
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

PAGE = Path(__file__).resolve().parent
WEBKIT = PAGE.parent


def read_locked(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f'{path.name} differs from its source lock')
    return data


def prepare(archive, output, patch_tool):
    recipe_sha256 = sha256(Path(__file__).read_bytes()).hexdigest()
    page_lock = (PAGE / 'source_lock.json').read_bytes()
    software = json.loads(page_lock)
    base = read_locked(WEBKIT / 'source_lock.json', software['base_lock_sha256'])
    upstream = json.loads(base)
    patches = [{'path': name, 'sha256': digest} for name, digest in sorted(upstream['patches'].items())]
    patches.extend(software['patches'])
    patch_data = [(entry['path'], read_locked(WEBKIT / entry['path'], entry['sha256'])) for entry in patches]
    platform_files = {Path(name).name: read_locked(WEBKIT / name, digest)
                      for name, digest in upstream['platform_sources'].items()}

    env = {**os.environ, 'LC_ALL': 'C'}
    patch_version = subprocess.check_output([patch_tool, '--version'], env=env)
    if not patch_version.startswith(b'GNU patch '):
        raise ValueError('Select GNU patch with --patch to apply the locked WebKit patches')

    with archive.open('rb') as stream:
        if (os.fstat(stream.fileno()).st_size != upstream['bytes']
                or file_digest(stream, 'sha256').hexdigest() != upstream['sha256']):
            raise ValueError('WPE WebKit archive differs from its source lock')
        stream.seek(0)
        output.mkdir(parents=True, exist_ok=False)
        sources = output / 'source'
        sources.mkdir()
        with tarfile.open(fileobj=stream, mode='r:xz') as bundle:
            bundle.extractall(sources, filter='data')

    source = sources / upstream['archive_root']
    with (output / 'patch.log').open('wb') as log:
        log.write(patch_version)
        for name, contents in patch_data:
            log.write(f'Applying {name}\n'.encode())
            log.flush()
            subprocess.run([patch_tool, '--batch', '--fuzz=0', '-N', '-p1', '-d', source],
                           input=contents, stdout=log, stderr=subprocess.STDOUT, env=env, check=True)

    platform = source / 'Source/WTF/wtf/xos'
    platform.mkdir()
    for name, contents in platform_files.items():
        (platform / name).write_bytes(contents)

    receipt = {
        'status': 'source_prepared',
        'source': f"source/{upstream['archive_root']}",
        'archive_sha256': upstream['sha256'],
        'base_lock_sha256': software['base_lock_sha256'],
        'software_lock_sha256': sha256(page_lock).hexdigest(),
        'recipe_sha256': recipe_sha256,
        'patches': patches,
        'platform_sources': upstream['platform_sources'],
        'patch_log_sha256': sha256((output / 'patch.log').read_bytes()).hexdigest(),
    }
    (output / 'manifest.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--patch', default=shutil.which('gpatch') or 'patch', help='GNU patch executable')
    args = parser.parse_args()
    prepare(args.archive, args.output, args.patch)


if __name__ == '__main__':
    main()
