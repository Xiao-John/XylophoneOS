# SPDX-License-Identifier: Apache-2.0
"""P3 offline repositories: bounded indexes, exact dependency locks and P1 handoff.

No network or publisher authentication is implied. A caller may pin the exact
lock bytes using an independently trusted SHA-256. Package paths are derived
from their digests, never accepted from metadata.
"""
import hashlib
import os
from pathlib import Path
import shutil
import stat
import tempfile

from xypm_format import (HEX, MAX_ARCHIVE, MAX_MANIFEST, canonical, check_profile,
                         fields, identifier, require, strict_json, text,
                         verify_package)

max_entries = 256
max_selected = 64
identity_fields = ('id', 'upstream_version', 'revision', 'sha256')
entry_fields = (*identity_fields, 'size', 'required_features', 'runtime_dependencies')


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def bounded_bytes(path):
    """Read one regular non-symlink metadata instance, with a hard read bound."""
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) |
                         getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(descriptor, 'rb') as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'metadata is not a regular file')
        data = stream.read(MAX_MANIFEST + 1)
    require(len(data) <= MAX_MANIFEST, 'repository metadata exceeds 1 MiB')
    return data


def exact_identity(value):
    identifier(value['id'])
    text(value['upstream_version'], 'version')
    require(type(value['revision']) is int and 0 <= value['revision'] < (1 << 31),
            'invalid repository revision')
    require(type(value['sha256']) is str and HEX.fullmatch(value['sha256']),
            'invalid repository package hash')
    return tuple(value[key] for key in identity_fields)


def validate_index(index, profile=None):
    fields(index, ('format_version', 'target_profile', 'packages'))
    require(type(index['format_version']) is int and index['format_version'] == 1,
            'unsupported repository index version')
    identifier(index['target_profile'])
    entries = index['packages']
    require(type(entries) is list and 0 < len(entries) <= max_entries,
            'invalid repository package count')
    previous, identities = '', set()
    for entry in entries:
        fields(entry, entry_fields)
        identity = exact_identity(entry)
        require(entry['sha256'] > previous, 'repository hashes must be unique and sorted')
        previous = entry['sha256']
        require(identity[:3] not in identities, 'ambiguous package version/revision')
        identities.add(identity[:3])
        require(type(entry['size']) is int and 0 < entry['size'] <= MAX_ARCHIVE and
                entry['size'] % 512 == 0, 'invalid repository package size')
        features = entry['required_features']
        require(type(features) is list and len(features) <= 64, 'invalid repository features')
        for feature in features:
            identifier(feature)
        require(features == sorted(set(features)), 'repository features must be unique and sorted')
        dependencies = entry['runtime_dependencies']
        require(type(dependencies) is list and len(dependencies) <= 128,
                'invalid repository dependency count')
        previous_id = ''
        for dependency in dependencies:
            fields(dependency, identity_fields)
            exact_identity(dependency)
            require(dependency['id'] > previous_id and dependency['id'] != entry['id'],
                    'duplicate/unsorted/self repository dependency')
            previous_id = dependency['id']
        if profile is not None:
            check_profile(dict(entry, target_profile=index['target_profile']), profile)
    return index


def resolve(index, roots):
    """Deterministic dependency-first DFS; there is never an implicit latest version."""
    require(type(roots) is list and 0 < len(roots) <= max_selected, 'invalid lock roots')
    for root in roots:
        require(type(root) is str and HEX.fullmatch(root), 'invalid root digest')
    require(roots == sorted(set(roots)), 'lock roots must be unique and sorted')
    by_digest = {entry['sha256']: entry for entry in index['packages']}
    chosen, states, ordered = {}, {}, []

    def visit(digest):
        require(digest in by_digest, 'repository dependency or root is missing')
        entry = by_digest[digest]
        require(entry['id'] not in chosen or chosen[entry['id']] == digest,
                'dependency closure selects conflicting package versions')
        chosen[entry['id']] = digest
        require(len(chosen) <= max_selected, 'lock dependency closure exceeds 64 packages')
        require(states.get(digest) != 1, 'repository dependency cycle')
        if states.get(digest) == 2:
            return
        states[digest] = 1
        for dependency in entry['runtime_dependencies']:
            target = by_digest.get(dependency['sha256'])
            require(target is not None and exact_identity(target) == exact_identity(dependency),
                    'repository dependency identity mismatch or missing package')
            visit(dependency['sha256'])
        states[digest] = 2
        ordered.append(digest)

    for root in roots:
        visit(root)
    return ordered


def load_index(repository, profile=None):
    repository = Path(repository)
    require(repository.is_dir() and not repository.is_symlink(), 'repository must be a real directory')
    data = bounded_bytes(repository / 'index.json')
    return validate_index(strict_json(data), profile), digest_bytes(data)


def make_lock(repository, roots, profile=None):
    index, index_sha256 = load_index(repository, profile)
    roots = sorted(roots)
    return {'format_version': 1, 'target_profile': index['target_profile'],
            'index_sha256': index_sha256, 'roots': roots, 'packages': resolve(index, roots)}


def validate_lock(lock, index, index_sha256):
    fields(lock, ('format_version', 'target_profile', 'index_sha256', 'roots', 'packages'))
    require(type(lock['format_version']) is int and lock['format_version'] == 1,
            'unsupported repository lock version')
    require(lock['target_profile'] == index['target_profile'], 'lock target profile mismatch')
    require(type(lock['index_sha256']) is str and HEX.fullmatch(lock['index_sha256']) and
            lock['index_sha256'] == index_sha256, 'lock/index SHA-256 mismatch')
    expected = resolve(index, lock['roots'])
    require(lock['packages'] == expected, 'lock is not the exact deterministic dependency closure')
    return lock


def entry_from_package(result):
    manifest = result['manifest']
    return {key: manifest[key] for key in identity_fields[:-1]} | {
        'sha256': result['sha256'], 'size': result['archive_size'],
        'required_features': sorted(manifest['required_features']),
        'runtime_dependencies': sorted(manifest['runtime_dependencies'], key=lambda item: item['id'])}


def verify_repository(repository, lock_path, profile=None, expected_lock_sha256=None):
    index, index_sha256 = load_index(repository, profile)
    lock_bytes = bounded_bytes(lock_path)
    lock_sha256 = digest_bytes(lock_bytes)
    if expected_lock_sha256 is not None:
        require(type(expected_lock_sha256) is str and HEX.fullmatch(expected_lock_sha256),
                'invalid expected lock hash')
        require(lock_sha256 == expected_lock_sha256, 'lock SHA-256 mismatch')
    lock = validate_lock(strict_json(lock_bytes), index, index_sha256)
    entries = {entry['sha256']: entry for entry in index['packages']}
    selected = []
    for digest in lock['packages']:
        package = Path(repository) / (digest + '.xpk')
        result = verify_package(package, profile, digest)
        entry = entries[digest]
        require(result['manifest']['target_profile'] == index['target_profile'],
                'repository package target profile mismatch')
        require(entry_from_package(result) == entry,
                'repository entry differs from package manifest/size')
        selected.append(entry)
    return {'status': 'verified_integrity_only', 'index_sha256': index_sha256,
            'lock_sha256': lock_sha256, 'target_profile': index['target_profile'],
            'packages': selected}


def write_metadata(output, value):
    """Publish complete metadata without overwriting an existing output."""
    output = Path(output)
    data = canonical(value)
    require(len(data) <= MAX_MANIFEST, 'repository metadata exceeds 1 MiB')
    with tempfile.NamedTemporaryFile(prefix='.xypm_metadata_', dir=output.parent) as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
        os.link(stream.name, output)
    return digest_bytes(data)


def create_repository(packages, output, profile):
    """Verify private copies before publishing the index as a completion marker."""
    require(0 < len(packages) <= max_entries, 'invalid repository package count')
    output = Path(output)
    output.mkdir(mode=0o700)  # Exclusive: never replace user files or follow a symlink.
    complete = False
    try:
        entries = []
        for ordinal, package in enumerate(packages):
            package = Path(package)
            require(package.is_file() and not package.is_symlink(), 'package must be a regular non-symlink file')
            require(package.stat().st_size <= MAX_ARCHIVE, 'repository source package exceeds size limit')
            temporary = output / ('.package_%d' % ordinal)
            # A bound also holds if the source grows during copying.
            descriptor = os.open(package, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) |
                                 getattr(os, 'O_NONBLOCK', 0))
            with os.fdopen(descriptor, 'rb') as source, temporary.open('xb') as target:
                require(stat.S_ISREG(os.fstat(source.fileno()).st_mode), 'package is not regular')
                remaining = MAX_ARCHIVE + 1
                while remaining:
                    block = source.read(min(65536, remaining))
                    if not block:
                        break
                    target.write(block)
                    remaining -= len(block)
                require(remaining > 0, 'repository source package exceeds size limit')
            result = verify_package(temporary, profile)
            entries.append(entry_from_package(result))
            os.link(temporary, output / (result['sha256'] + '.xpk'))
            temporary.unlink()
        index = {'format_version': 1, 'target_profile': profile['id'],
                 'packages': sorted(entries, key=lambda entry: entry['sha256'])}
        validate_index(index, profile)
        index_sha256 = write_metadata(output / 'index.json', index)
        complete = True
        return {'status': 'created_integrity_only', 'index_sha256': index_sha256,
                'packages': len(entries), 'repository': str(output)}
    finally:
        if not complete:
            shutil.rmtree(output)


def transact_locked(repository, lock, package_id, image, output, profile, operation,
                    expected_lock_sha256=None, *, require_initialized=False):
    """One explicit P1 transaction after complete offline closure verification.

    P1 reopens the selected package, verifies the pinned digest while staging its
    bytes, then publishes only a completely verified candidate image. A changed
    pathname can therefore fail, but cannot substitute unverified install bytes.
    """
    require(operation in ('install', 'upgrade'), 'unsupported repository transaction')
    identifier(package_id)
    verified = verify_repository(repository, lock, profile, expected_lock_sha256)
    entry = next((entry for entry in verified['packages'] if entry['id'] == package_id), None)
    require(entry is not None, 'package is not selected by lock')
    from xypm_image import transact
    result = transact(image, output, profile, operation,
                      package=Path(repository) / (entry['sha256'] + '.xpk'),
                      expected_sha256=entry['sha256'], require_initialized=require_initialized)
    return dict(result, index_sha256=verified['index_sha256'], lock_sha256=verified['lock_sha256'])
