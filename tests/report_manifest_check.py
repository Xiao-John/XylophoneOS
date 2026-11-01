#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify flat per-directory evidence manifests (evidence_integrity contract).

Directories created after the contract date carry manifest.json
({"version": 1, "files": {relpath: sha256}}) covering every other file in the
directory; leaves never embed each other's hashes and git remains the single
trust root. Older directories keep their legacy verification and are reported
as grandfathered, never as covered.
"""
import hashlib
import json
import re
import sys
import tarfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'docs' / 'reports'
# Exact pre-contract index bytes from the original Notes and Browser drafts.
# This does not exempt paths or other files from public-path scanning.
legacy_hygiene_indexes = {
    'ccfd18a5fa3266a2ebeb59dc49421be2bad8bb5bbed85527172c92bae52287b1',
    '3b388826a5778d00edefe5bd03bd6f84aab404fbbf9cddc483f5f77e27717610',
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def check_legacy_dock(directory, data):
    """Verify the pre-contract Dock bundle's own legacy member index."""
    expected = data.get('bundle_entries_sha256')
    bundle = directory / 'evidence_bundle.tar.gz'
    if not isinstance(expected, dict) or not expected or not bundle.is_file():
        raise ValueError('missing legacy bundle or member index')
    if data.get('bundle_sha256') != sha256(bundle):
        raise ValueError('legacy bundle hash mismatch')
    actual = {}
    total = 0
    with tarfile.open(bundle, 'r:gz') as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if (not member.isfile() or path.is_absolute() or '..' in path.parts or
                    member.name in actual or member.size > 256 * 1024 * 1024):
                raise ValueError('unsafe or duplicate legacy archive member')
            total += member.size
            if len(actual) >= 20000 or total > 1024 * 1024 * 1024:
                raise ValueError('legacy archive exceeds verification limits')
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError('unreadable legacy archive member')
            digest = hashlib.sha256()
            with stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            actual[member.name] = digest.hexdigest()
    if any(not isinstance(v, str) or not re.fullmatch(r'[0-9a-f]{64}', v) for v in expected.values()):
        raise ValueError('invalid legacy member hash')
    if actual != expected:
        raise ValueError('legacy bundle members or hashes differ from index')
    return len(actual)


def check_legacy_hygiene(directory):
    index = directory / 'SHA256SUMS'
    if sha256(index) not in legacy_hygiene_indexes:
        raise ValueError('unrecognized pre-contract hygiene index')
    seen = set()
    for line in index.read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        if not match or match.group(2) in seen:
            raise ValueError('malformed or duplicate legacy hygiene entry')
        digest, name = match.groups()
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name:
            raise ValueError('unsafe legacy hygiene path')
        target = directory / name
        if target.is_symlink() or not target.is_file() or sha256(target) != digest:
            raise ValueError('legacy hygiene entry missing or mismatched')
        seen.add(name)
    if not seen:
        raise ValueError('empty legacy hygiene index')
    return len(seen)


def check_reports(reports):
    compliant, grandfathered, legacy_verified, failures = [], [], [], []
    for directory in sorted(p for p in reports.iterdir() if p.is_dir()):
        manifest = directory / 'manifest.json'
        legacy_hygiene = None
        if directory.name == 'issue37_path_hygiene' and (directory / 'SHA256SUMS').is_file():
            try:
                legacy_hygiene = check_legacy_hygiene(directory)
            except (OSError, UnicodeError, ValueError) as error:
                failures.append(f'{directory.name}: {error}')
                continue
        if not manifest.is_file():
            grandfathered.append(directory.name)
            if legacy_hygiene is not None:
                legacy_verified.append({'directory': directory.name, 'scope': 'legacy_index_only', 'members': legacy_hygiene})
            continue
        try:
            data = json.loads(manifest.read_text(), object_pairs_hook=unique_object)
        except ValueError as error:
            failures.append(f'{directory.name}: invalid manifest JSON: {error}')
            continue
        if not isinstance(data, dict):
            failures.append(f'{directory.name}: manifest must be an object')
            continue
        if directory.name == 'aurora_midnight_dock_20261030' and 'version' not in data:
            try:
                count = check_legacy_dock(directory, data)
                grandfathered.append(directory.name)
                legacy_verified.append({'directory': directory.name, 'scope': 'bundle_and_members_only', 'members': count})
            except (OSError, EOFError, ValueError, tarfile.TarError) as error:
                failures.append(f'{directory.name}: {error}')
            continue
        if data.get('version') != 1 or not isinstance(data.get('files'), dict):
            failures.append(f'{directory.name}: manifest must be {{"version": 1, "files": {{...}}}}')
            continue
        listed = data['files']
        actual = {p.relative_to(directory).as_posix()
                  for p in sorted(directory.rglob('*')) if p.is_file()
                  and p != manifest}
        problems = []
        for relative, digest in sorted(listed.items()):
            path = PurePosixPath(relative)
            if (not relative or '\\' in relative or path.is_absolute() or '..' in path.parts or
                    not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest)):
                problems.append('unsafe path or invalid hash in manifest')
                continue
            target = directory / relative
            parent = directory
            unsafe = False
            for part in path.parts:
                parent = parent / part
                if parent.is_symlink():
                    unsafe = True
                    break
            if unsafe:
                problems.append(f'symlink not supported: {relative}')
            elif not target.is_file():
                problems.append(f'missing file: {relative}')
            elif sha256(target) != digest:
                problems.append(f'hash mismatch: {relative}')
        for relative in sorted(actual - set(listed)):
            problems.append(f'file not in manifest: {relative}')
        for relative in sorted(set(listed) - actual):
            problems.append(f'manifest lists absent file: {relative}')
        if problems:
            failures.extend(f'{directory.name}: {line}' for line in problems)
        elif legacy_hygiene is not None:
            grandfathered.append(directory.name)
            legacy_verified.append({'directory': directory.name, 'scope': 'legacy_index_and_flat_manifest', 'members': legacy_hygiene})
        else:
            compliant.append(directory.name)
    return {'status': 'passed' if not failures else 'failed',
            'compliant': compliant, 'grandfathered': grandfathered,
            'legacy_verified': legacy_verified, 'failures': failures}


def main():
    report = check_reports(REPORTS)
    print(json.dumps(report, indent=1))
    return 1 if report['failures'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
