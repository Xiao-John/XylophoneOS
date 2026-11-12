#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the lexical COW0 inventory and its drift check."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cow0_source_audit', ROOT / 'scripts/cow0_source_audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class Cow0SourceAuditTest(unittest.TestCase):
    def test_inventory_discovers_new_sites_and_direct_physical_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'src/kernel/new.cpp'
            source.parent.mkdir(parents=True)
            source.write_text('void copy_to_user(int x);\ncopy_to_user(a, b, n);\n'
                              'auto *p = reinterpret_cast<u64*>(physical);\n', encoding='utf-8')
            with mock.patch.object(audit, 'ROOT', root), mock.patch.object(audit, 'REVIEWED', ()):
                report = audit.inventory()
            self.assertEqual([entry['kinds'] for entry in report['sites']],
                             [['copy_to_user'], ['physical_direct_candidate']])
            self.assertEqual([entry['line'] for entry in report['sites']], [2, 3])
            self.assertIn('src/kernel/new.cpp', report['files_sha256'])

    def test_check_rejects_changed_or_new_write_sites(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'src/kernel/example.cpp'
            source.parent.mkdir(parents=True)
            source.write_text('copy_to_user(a, b, n);\n', encoding='utf-8')
            output = root / 'audit.json'
            with mock.patch.object(audit, 'ROOT', root), mock.patch.object(audit, 'OUTPUT', output), \
                 mock.patch.object(audit, 'REVIEWED', ()), mock.patch('sys.argv', ['audit', '--check']):
                output.write_text(json.dumps(audit.inventory()), encoding='utf-8')
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(audit.main(), 0)
                source.write_text('copy_to_user(a, b, n);\ncopy_to_user(c, d, n);\n', encoding='utf-8')
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(audit.main(), 1)

    def test_write_cannot_mislabel_a_changed_baseline(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'src/kernel/example.cpp'
            source.parent.mkdir(parents=True)
            source.write_text('copy_to_user(a, b, n);\n', encoding='utf-8')
            output = root / 'audit.json'
            result = mock.Mock(returncode=0, stdout=b'different baseline bytes')
            with mock.patch.object(audit, 'ROOT', root), mock.patch.object(audit, 'OUTPUT', output), \
                 mock.patch.object(audit, 'REVIEWED', ()), mock.patch.object(audit.subprocess, 'run', return_value=result), \
                 mock.patch('sys.argv', ['audit', '--write']), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(audit.main(), 1)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
