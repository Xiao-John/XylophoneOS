#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import review_evidence_guest_findings as guest_review
import verify_evidence_migration as migration
import check_public_evidence_paths as scanner


class guest_finding_review_tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'docs/reports/example/report.json'
        self.path.parent.mkdir(parents=True)
        self.guest_temp = '/tm' + 'p/fixture'
        data = {'host': '/Us' + 'ers/example/project',
                'commands': [{'command': 'cat /tests/fixture'}],
                'host_reference': {'negative': {'input': self.guest_temp}}}
        self.original = json.dumps(data).encode()
        self.path.write_bytes(self.original)
        self.git('init', '-q')
        self.git('add', 'docs')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'source')
        self.source = self.git('rev-parse', 'HEAD')
        self.export = migration.expected_export(self.original, 'report.json')
        self.path.write_bytes(self.export)
        self.convert = self.root / migration.conversion_dir
        self.convert.mkdir(parents=True)
        self.ledger = {'status': 'DERIVED_SANITIZED_EXPORT', 'source_commit': self.source,
                       'changes': [{'path': 'docs/reports/example/report.json',
                                    'original_sha256': migration.digest(self.original),
                                    'export_sha256': migration.digest(self.export)}]}
        findings = []
        scanner.scan(self.export, 'docs/reports/example/report.json', findings)
        counts = {}
        for item in findings:
            counts[item['category']] = counts.get(item['category'], 0) + 1
        self.plan = {'version': 1, 'records': [{'path': 'docs/reports/example/report.json',
                     'ledger': 'example_lineage.json', 'classification': 'GUEST_TEST_DATA', 'findings': counts}]}
        self.commit_export()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.PIPE, text=True).strip()

    def commit_export(self):
        (self.convert / 'example_lineage.json').write_text(json.dumps(self.ledger))
        (self.convert / 'reviewed_guest_findings.json').write_text(json.dumps(self.plan))
        files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.convert.iterdir() if p.name != 'manifest.json'}
        (self.convert / 'manifest.json').write_text(json.dumps({'version': 1, 'files': files}))
        self.git('add', 'docs')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'export')

    def test_exact_source_identical_guest_data_is_reviewed(self):
        result = guest_review.review(self.root, self.source, 'HEAD', ['distinct-private-id'])
        self.assertEqual(result['status'], 'PASS_WITH_REVIEWED_GUEST_FIXTURES')
        self.assertEqual(result['reviewed_files'], 1)

    def test_private_path_category_cannot_be_approved(self):
        self.plan['records'][0]['findings']['macos_home'] = 1
        self.commit_export()
        with self.assertRaises(ValueError):
            guest_review.review(self.root, self.source, 'HEAD', ['distinct-private-id'])

    def test_guest_data_tampering_fails_even_after_hash_update(self):
        changed = self.export.replace(self.guest_temp.encode(), ('/tm' + 'p/other').encode())
        self.path.write_bytes(changed)
        self.ledger['changes'][0]['export_sha256'] = migration.digest(changed)
        self.commit_export()
        with self.assertRaises(ValueError):
            guest_review.review(self.root, self.source, 'HEAD', ['distinct-private-id'])

    def test_untemplated_host_command_is_rejected(self):
        data = {'qemu_command': ['/opt/custom/qemu-system-x86_64']}
        with self.assertRaises(ValueError):
            guest_review.inspect_guest_data(data, data)


if __name__ == '__main__':
    unittest.main()
