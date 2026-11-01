#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify the PR20 path-only evidence derivative against its frozen source.

The historical result and input hashes remain claims about the original run;
this verifies byte provenance and old/new report indexes, not guest replay.
"""
import argparse
import gzip
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from evidence_host_command_templates import template_qemu_json
from verify_evidence_index import checkout_reader, git_reader, no_duplicates, safe_path

SOURCE = 'da1a47c0b8455be82ba90aaf5bea393066839ac4'
EXPORT = 'docs/evidence_exports/issue37_pr20'
REPORTS = ('docs/reports/net_clock_irq_repair_20261029',
           'docs/reports/virtio_net_n1_20261029')
HOST_LOG = REPORTS[0] + '/regressions/n1_quota_reclaim/runner.log.gz'
NOTICE = (b'> **Evidence version:** This is a path-sanitized derivative. '
          b'The original bytes and historical input hashes belong to the source Git commit; '
          b'old/new file hashes are recorded in the '
          b'[conversion ledger](../../evidence_exports/issue37_pr20/lineage.json).\n\n')
ADDED_NOTICE = (b'# VirtIO-Net N1 evidence derivative\n\n'
                b'This directory is a path-sanitized derivative of the original PR20 '
                b'evidence; historical outcomes and input hashes belong to the source commit. '
                b'See the [conversion ledger](../../evidence_exports/issue37_pr20/lineage.json). '
                b'The original-format checksum index covers the original 424 indexed files; '
                b'this added notice is covered by Git and the conversion ledger.\n')
PATTERNS = (
    ('WORKTREE', re.compile(rb'(?i)/us' rb'ers/[^/\s"\'\\]+/Documents/ChatGPT/os/[^/\s,;"\'\\]+')),
    ('TOOLCHAIN', re.compile(rb'(?i)/us' rb'ers/[^/\s"\'\\]+/homebrew')),
    ('HOME', re.compile(rb'(?i)/us' rb'ers/[^/\s,;"\'\\]+')),
    ('PYTHON', re.compile(rb'/Library/Frame' rb'works/Python\.framework/Versions/[^/\s,;"\'\\]+')),
)
HOST_SOCKET = re.compile(rb'(?<=unix:)/var/fol' rb'ders/[^/\s,;"\'\\]+')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def transformed(raw, name):
    """Change host roots and recognized QEMU command tokens only."""
    for kind, pattern in PATTERNS:
        raw = pattern.sub(lambda m: ('${XOS_' + kind + '_' + digest(m.group())[:12].upper() + '}').encode(), raw)
    raw, _, skipped = template_qemu_json(raw)
    if skipped:
        raise ValueError('ambiguous QEMU token')
    if name == HOST_LOG:
        raw = HOST_SOCKET.sub(lambda m: ('${XOS_HOST_TEMP_' + digest(m.group())[:12].upper() + '}').encode(), raw)
    if name == REPORTS[0] + '/README.md':
        raw = NOTICE + raw
    return raw


def payload(data):
    return gzip.decompress(data) if data.startswith(b'\x1f\x8b') else data


def check(value, message):
    if not value:
        raise ValueError(message)


def run(root, revision=None):
    source = git_reader(root, SOURCE)
    export = git_reader(root, revision) if revision else checkout_reader(root)
    try:
        manifest = json.loads(export.read(safe_path(EXPORT + '/manifest.json')), object_pairs_hook=no_duplicates)
        check(manifest.get('version') == 1 and set(manifest.get('files', {})) == {'README.md', 'lineage.json'}, 'invalid flat manifest')
        for name, expected in manifest['files'].items():
            check(digest(export.read(safe_path(EXPORT + '/' + name))) == expected, 'manifest mismatch')
        ledger = json.loads(export.read(safe_path(EXPORT + '/lineage.json')), object_pairs_hook=no_duplicates)
        check(ledger.get('source_commit') == SOURCE and ledger.get('status') == 'DERIVED_SANITIZED_EXPORT', 'invalid source')
        notice_name = REPORTS[1] + '/README.md'
        check(notice_name not in source.modes, 'added notice already exists in source')
        check(export.read(safe_path(notice_name)) == ADDED_NOTICE and
              ledger['added_notice']['path'] == notice_name and
              ledger['added_notice']['sha256'] == digest(ADDED_NOTICE), 'added notice mismatch')
        changes = {}
        for item in ledger['changes']:
            name = str(safe_path(item['path']))
            check(any(name.startswith(report + '/') for report in REPORTS), 'unexpected changed path')
            check(name not in changes, 'duplicate changed path')
            old, new = source.read(safe_path(name)), export.read(safe_path(name))
            check(digest(old) == item['original_sha256'] and digest(new) == item['export_sha256'], 'changed hash mismatch')
            check(old.startswith(b'\x1f\x8b') == new.startswith(b'\x1f\x8b'), 'gzip type changed')
            check(transformed(payload(old), name) == payload(new), 'non-path payload change')
            changes[name] = item
        checks = 0
        observed_changes = set()
        for report in REPORTS:
            index_name = report + '/checksums.json'
            old_index_data = source.read(safe_path(index_name))
            new_index_data = export.read(safe_path(index_name))
            recorded = ledger['indexes'][index_name]
            check(digest(old_index_data) == recorded['original_sha256'] and
                  digest(new_index_data) == recorded['export_sha256'], 'index provenance mismatch')
            old_index = json.loads(old_index_data, object_pairs_hook=no_duplicates)
            new_index = json.loads(new_index_data, object_pairs_hook=no_duplicates)
            check(set(old_index) == set(new_index), 'index entries changed')
            for relative, expected in old_index.items():
                name = str(safe_path(report + '/' + str(safe_path(relative))))
                old, new = source.read(safe_path(name)), export.read(safe_path(name))
                check(digest(old) == expected and digest(new) == new_index[relative], 'indexed file mismatch')
                if old != new:
                    observed_changes.add(name)
                    check(name in changes, 'unrecorded indexed change')
                checks += 1
        check(observed_changes == set(changes), 'ledger contains missing or unchanged entries')
        return {'status': 'PASS', 'scope': 'conversion and legacy indexes only; original run not rebound',
                'source_commit': SOURCE, 'changed_files': len(changes), 'legacy_index_entries': checks}
    finally:
        source.close()
        export.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--export-revision')
    args = parser.parse_args()
    try:
        result = run(args.root, args.export_revision)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'FAIL', 'error_type': type(error).__name__}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
