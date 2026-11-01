#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import report_manifest_check as checker


class report_manifest_tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def legacy(self, name='aurora_midnight_dock_20261030', duplicate=False):
        directory = self.root / name
        directory.mkdir()
        payload = b'legacy evidence\n'
        with tarfile.open(directory / 'evidence_bundle.tar.gz', 'w:gz') as archive:
            for _ in range(2 if duplicate else 1):
                info = tarfile.TarInfo('run/report.json')
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
        bundle = (directory / 'evidence_bundle.tar.gz').read_bytes()
        manifest = {'bundle_sha256': hashlib.sha256(bundle).hexdigest(),
                    'bundle_entries_sha256': {'run/report.json': hashlib.sha256(payload).hexdigest()}}
        (directory / 'manifest.json').write_text(json.dumps(manifest))
        return directory

    def test_known_legacy_bundle_is_grandfathered_and_scoped(self):
        self.legacy()
        result = checker.check_reports(self.root)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['grandfathered'], ['aurora_midnight_dock_20261030'])
        self.assertEqual(result['legacy_verified'][0]['scope'], 'bundle_and_members_only')
        self.assertEqual(result['legacy_verified'][0]['members'], 1)

    def test_legacy_hash_corruption_and_duplicate_members_fail(self):
        directory = self.legacy()
        manifest = json.loads((directory / 'manifest.json').read_text())
        manifest['bundle_entries_sha256']['run/report.json'] = '0' * 64
        (directory / 'manifest.json').write_text(json.dumps(manifest))
        self.assertEqual(checker.check_reports(self.root)['status'], 'failed')
        other = self.root / 'other'
        other.mkdir()
        self.legacy(name='other/aurora_midnight_dock_20261030', duplicate=True)
        result = checker.check_reports(other)
        self.assertEqual(result['status'], 'failed')

    def test_unknown_legacy_shape_is_not_whitelisted(self):
        self.legacy(name='new_unregistered_report')
        self.assertEqual(checker.check_reports(self.root)['status'], 'failed')

    def test_exact_legacy_hygiene_index_is_scoped_and_not_broadly_allowed(self):
        directory = self.root / 'issue37_path_hygiene'
        directory.mkdir()
        (directory / 'README.md').write_bytes(b'legacy')
        index = (hashlib.sha256(b'legacy').hexdigest() + '  README.md\n').encode()
        (directory / 'SHA256SUMS').write_bytes(index)
        index_hash = hashlib.sha256(index).hexdigest()
        self.assertEqual(checker.check_reports(self.root)['status'], 'failed')
        with patch.object(checker, 'legacy_hygiene_indexes', {index_hash}):
            result = checker.check_reports(self.root)
            self.assertEqual(result['status'], 'passed')
            self.assertEqual(result['legacy_verified'][0]['scope'], 'legacy_index_only')
            (directory / 'README.md').write_bytes(b'altered')
            self.assertEqual(checker.check_reports(self.root)['status'], 'failed')

    def test_flat_manifest_rejects_changed_missing_extra_and_unsafe_files(self):
        directory = self.root / 'new_report'
        directory.mkdir()
        (directory / 'data.txt').write_bytes(b'good')
        manifest = {'version': 1, 'files': {'data.txt': hashlib.sha256(b'good').hexdigest()}}
        (directory / 'manifest.json').write_text(json.dumps(manifest))
        self.assertEqual(checker.check_reports(self.root)['status'], 'passed')
        (directory / 'data.txt').write_bytes(b'changed')
        self.assertEqual(checker.check_reports(self.root)['status'], 'failed')
        (directory / 'data.txt').unlink()
        self.assertEqual(checker.check_reports(self.root)['status'], 'failed')
        (directory / 'data.txt').write_bytes(b'good')
        (directory / 'extra.txt').write_bytes(b'extra')
        self.assertEqual(checker.check_reports(self.root)['status'], 'failed')
        (directory / 'extra.txt').unlink()
        manifest['files']['../outside'] = '0' * 64
        (directory / 'manifest.json').write_text(json.dumps(manifest))
        self.assertEqual(checker.check_reports(self.root)['status'], 'failed')

    def test_symlink_and_duplicate_json_keys_fail(self):
        directory = self.root / 'new_report'
        directory.mkdir()
        (directory / 'target.txt').write_bytes(b'good')
        (directory / 'link.txt').symlink_to('target.txt')
        digest = hashlib.sha256(b'good').hexdigest()
        (directory / 'manifest.json').write_text(json.dumps({'version': 1, 'files': {'target.txt': digest, 'link.txt': digest}}))
        self.assertEqual(checker.check_reports(self.root)['status'], 'failed')
        (directory / 'manifest.json').write_text('{"version":1,"version":1,"files":{}}')
        self.assertEqual(checker.check_reports(self.root)['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
