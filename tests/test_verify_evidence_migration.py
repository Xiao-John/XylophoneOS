#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import verify_evidence_migration as migration


class evidence_migration_tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report = self.root / 'docs/reports/example'
        self.report.mkdir(parents=True)
        self.guest_path = b'/tm' + b'p/guest'
        self.old = b'{"host":"' + b'/Us' + b'ers/example/project", "guest":"' + self.guest_path + b'"}\n'
        self.path = self.report / 'report.json'
        self.path.write_bytes(self.old)
        self.git('init', '-q')
        self.git('add', 'docs')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'source')
        self.source = self.git('rev-parse', 'HEAD')
        self.new = migration.expected_export(self.old)
        self.path.write_bytes(self.new)
        self.convert = self.root / migration.conversion_dir
        self.convert.mkdir(parents=True)
        self.ledger = {'status': 'DERIVED_SANITIZED_EXPORT', 'source_commit': self.source,
                       'changes': [{'path': 'docs/reports/example/report.json',
                                    'original_sha256': migration.digest(self.old),
                                    'export_sha256': migration.digest(self.new)}]}
        self.write_ledger()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.PIPE, text=True).strip()

    def write_ledger(self):
        (self.convert / 'example_lineage.json').write_text(json.dumps(self.ledger))
        files = {'example_lineage.json': migration.digest((self.convert / 'example_lineage.json').read_bytes())}
        (self.convert / 'manifest.json').write_text(json.dumps({'version': 1, 'files': files}))

    def test_source_and_export_are_both_bound_to_git(self):
        result = migration.run(self.root)
        self.assertEqual((result['status'], result['changed_files']), ('PASS', 1))
        self.git('add', 'docs')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'export')
        self.assertEqual(migration.run(self.root, 'HEAD')['status'], 'PASS')

    def test_guest_tmp_change_is_rejected_even_if_hashes_are_updated(self):
        altered = self.new.replace(self.guest_path, b'/tm' + b'p/other')
        self.path.write_bytes(altered)
        self.ledger['changes'][0]['export_sha256'] = migration.digest(altered)
        self.write_ledger()
        with self.assertRaisesRegex(ValueError, 'non-path changes'):
            migration.run(self.root)

    def test_wrong_source_and_unlisted_leaf_fail(self):
        self.ledger['changes'][0]['original_sha256'] = '0' * 64
        self.write_ledger()
        with self.assertRaises(ValueError):
            migration.run(self.root)
        self.ledger['changes'][0]['original_sha256'] = migration.digest(self.old)
        self.write_ledger()
        (self.convert / 'unlisted.txt').write_text('unexpected')
        with self.assertRaisesRegex(ValueError, 'coverage'):
            migration.run(self.root)

    def test_index_input_metadata_cannot_be_rebound(self):
        old = {'inputs': {'image_sha256': '1' * 64}, 'files': {'report.json': '2' * 64}}
        new = {'inputs': {'image_sha256': '3' * 64}, 'files': {'report.json': '4' * 64}}
        with self.assertRaisesRegex(ValueError, 'qualification metadata'):
            migration.verify_index_semantics(json.dumps(old).encode(), json.dumps(new).encode(),
                                             {'original_index_path': 'docs/reports/example/index.json', 'index_field': 'files'})

    def test_host_document_notice_does_not_change_guest_text(self):
        name = 'docs/work_log/0063_input_edit_design.md'
        old = b'# History\nUse ' + b'/tm' + b'p/host-root/file\n'
        expected = migration.expected_export(old, name)
        self.assertIn(b'${XOS_DOC_TEMP_', expected)
        self.assertTrue((migration.host_document_notice + expected).endswith(expected))

    def test_unlisted_archive_member_change_is_rejected(self):
        def archive(second):
            out = io.BytesIO()
            with tarfile.open(fileobj=out, mode='w:gz') as tar:
                for name, data in [('one', b'one'), ('two', second)]:
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    tar.addfile(info, io.BytesIO(data))
            return out.getvalue()
        old = archive(b'two')
        changed = archive(b'tampered')
        info = {'member_count': 2, 'original_member_sha256': {'one': migration.digest(b'one'), 'two': migration.digest(b'two')},
                'changed_members': [], 'unchanged_member_count': 2, 'archive_owner_names_redacted': 0}
        with self.assertRaisesRegex(ValueError, 'unrecorded archive member change'):
            migration.verify_archive(old, changed, info)


if __name__ == '__main__':
    unittest.main()
