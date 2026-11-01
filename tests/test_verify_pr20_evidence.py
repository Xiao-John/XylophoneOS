#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Controls for source-bound PR20 path conversions and legacy indexes."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import verify_pr20_evidence as subject


class Reader:
    def __init__(self, files):
        self.files = files
        self.modes = {name: b'100644' for name in files}

    def read(self, path):
        return self.files[str(path)]

    def close(self):
        pass


def fixture(tamper=False, drop_index_entry=False):
    original, exported = {}, {}
    changes, indexes = [], {}
    personal = '/Us' + 'ers/example/work/project'
    guest = '/t' + 'mp/guest-input'
    qmp = '/var/fol' + 'ders/sample/qmp.sock'
    for report in subject.REPORTS:
        name = report + '/fixture.json'
        old = json.dumps({'host': personal, 'guest': guest,
                          'qemu_command': ['qemu-system-x86_64', '-qmp', 'unix:' + qmp]}).encode()
        new = subject.transformed(old, name)
        if tamper:
            new = new.replace(guest.encode(), (guest + '-altered').encode())
        original[name], exported[name] = old, new
        changes.append({'path': name, 'original_sha256': subject.digest(old), 'export_sha256': subject.digest(new)})
        index_name = report + '/checksums.json'
        old_index = json.dumps({'fixture.json': subject.digest(old)}).encode()
        new_index = json.dumps({} if drop_index_entry else {'fixture.json': subject.digest(new)}).encode()
        original[index_name], exported[index_name] = old_index, new_index
        indexes[index_name] = {'original_sha256': subject.digest(old_index), 'export_sha256': subject.digest(new_index)}
    notice = subject.REPORTS[1] + '/README.md'
    exported[notice] = subject.ADDED_NOTICE
    ledger = {'status': 'DERIVED_SANITIZED_EXPORT', 'source_commit': subject.SOURCE,
              'changes': changes, 'indexes': indexes,
              'added_notice': {'path': notice, 'sha256': subject.digest(subject.ADDED_NOTICE)}}
    exported[subject.EXPORT + '/lineage.json'] = json.dumps(ledger).encode()
    exported[subject.EXPORT + '/README.md'] = b'fixture conversion notes\n'
    manifest = {'version': 1, 'files': {name: subject.digest(exported[subject.EXPORT + '/' + name])
                                       for name in ('README.md', 'lineage.json')}}
    exported[subject.EXPORT + '/manifest.json'] = json.dumps(manifest).encode()
    return original, exported


class MigrationTests(unittest.TestCase):
    def run_fixture(self, **kwargs):
        original, exported = fixture(**kwargs)
        with patch.object(subject, 'git_reader', return_value=Reader(original)), \
                patch.object(subject, 'checkout_reader', return_value=Reader(exported)):
            return subject.run(Path('.'))

    def test_source_and_both_indexes_are_verified(self):
        result = self.run_fixture()
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual((result['changed_files'], result['legacy_index_entries']), (2, 2))

    def test_rehashed_guest_mutation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'non-path payload change'):
            self.run_fixture(tamper=True)

    def test_rehashed_missing_index_entry_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'index entries changed'):
            self.run_fixture(drop_index_entry=True)

    def test_log_socket_is_scoped_to_reviewed_log(self):
        socket = b'unix:/var/fol' + b'ders/example/qmp.sock'
        other = b'/t' + b'mp/guest-input'
        original = socket + b' ' + other
        self.assertIn(other, subject.transformed(original, subject.HOST_LOG))
        self.assertNotIn(socket, subject.transformed(original, subject.HOST_LOG))
        self.assertEqual(original, subject.transformed(original, 'unreviewed.log'))


if __name__ == '__main__':
    unittest.main()
