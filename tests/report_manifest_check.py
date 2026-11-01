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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'docs' / 'reports'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    compliant, grandfathered, failures = [], [], []
    for directory in sorted(p for p in REPORTS.iterdir() if p.is_dir()):
        manifest = directory / 'manifest.json'
        if not manifest.is_file():
            grandfathered.append(directory.name)
            continue
        try:
            data = json.loads(manifest.read_text())
        except ValueError as error:
            failures.append(f'{directory.name}: invalid manifest JSON: {error}')
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
            target = directory / relative
            if not target.is_file():
                problems.append(f'missing file: {relative}')
            elif sha256(target) != digest:
                problems.append(f'hash mismatch: {relative}')
        for relative in sorted(actual - set(listed)):
            problems.append(f'file not in manifest: {relative}')
        for relative in sorted(set(listed) - actual):
            problems.append(f'manifest lists absent file: {relative}')
        if problems:
            failures.extend(f'{directory.name}: {line}' for line in problems)
        else:
            compliant.append(directory.name)
    report = {'status': 'passed' if not failures else 'failed',
              'compliant': compliant, 'grandfathered': grandfathered,
              'failures': failures}
    print(json.dumps(report, indent=1))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
