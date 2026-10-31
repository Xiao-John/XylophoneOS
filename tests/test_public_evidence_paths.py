#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import gzip
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import check_public_evidence_paths as scanner
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ssg_public_paths import portable


class PublicPathTests(unittest.TestCase):
    def findings(self, data, expected=''):
        result = []
        scanner.scan(data, 'fixture', result, expected=expected)
        return result

    def categories(self, data, expected=''):
        return {f['category'] for f in self.findings(data, expected)}

    def test_private_paths_in_markdown_json_binary_and_utf16(self):
        home = b'/Users/' + b'example_dev/work'
        linux = b'/home/' + b'example_dev/work'
        windows = b'C:\\Users\\' + b'example_dev\\work'
        examples = [(b'# log\n' + home, 'macos_home'),
                    (b'\x00prefix ' + linux + b'\x00suffix', 'linux_home'),
                    (json.dumps({'command': windows.decode()}).encode(), 'windows_home'),
                    (home.decode().encode('utf-16-le'), 'macos_home'),
                    (b'file://' + linux, 'local_file_uri')]
        for value, category in examples:
            with self.subTest(category=category):
                self.assertIn(category, self.categories(value))

    def test_nested_zip_gzip_tar_member_content_name_and_link(self):
        tar = io.BytesIO()
        with tarfile.open(fileobj=tar, mode='w') as archive:
            data = b'\x00prefix /home/' + b'example_dev/private\x00suffix'
            item = tarfile.TarInfo('serial.bin')
            item.size = len(data)
            archive.addfile(item, io.BytesIO(data))
            item = tarfile.TarInfo('/Users/' + 'example_dev/archive-name')
            item.type = tarfile.SYMTYPE
            item.linkname = '/home/' + 'example_dev/link-target'
            archive.addfile(item)
        zipped = io.BytesIO()
        with zipfile.ZipFile(zipped, 'w') as archive:
            archive.writestr('evidence.tar.gz', gzip.compress(tar.getvalue()))
        findings = self.findings(zipped.getvalue(), 'outer.zip')
        locations = [f['location'] for f in findings]
        self.assertTrue(any('!name' in loc for loc in locations))
        self.assertTrue(any('!link' in loc for loc in locations))
        self.assertIn('linux_home', {f['category'] for f in findings})
        self.assertNotIn('example_dev', json.dumps(findings))

    def test_zip_symlink_target_and_member_name(self):
        zipped = io.BytesIO()
        with zipfile.ZipFile(zipped, 'w') as archive:
            item = zipfile.ZipInfo('/Users/' + 'example_dev/link')
            item.create_system = 3
            item.external_attr = (0o120777 << 16)
            archive.writestr(item, '/home/' + 'example_dev/target')
        findings = self.findings(zipped.getvalue(), 'links.zip')
        self.assertEqual({'macos_home', 'linux_home'}, {f['category'] for f in findings})

    def test_archive_owner_metadata_and_json_escapes(self):
        tar = io.BytesIO()
        with tarfile.open(fileobj=tar, mode='w') as archive:
            item = tarfile.TarInfo('safe.txt')
            item.uname = 'example_dev'
            archive.addfile(item, io.BytesIO())
        findings = []
        scanner.scan(tar.getvalue(), 'fixture', findings, budget=scanner.Budget(['example_dev']))
        self.assertTrue(any(f['category'] == 'private_identity' and '!metadata' in f['location'] for f in findings))
        encoded = b'{"command":"\\u002fUsers\\u002f' + b'example_dev\\u002fwork"}'
        self.assertIn('macos_home', self.categories(encoded))

    def test_unreadable_and_limited_archives_are_unverified(self):
        for data, name in [(b'\x1f\x8bnotgzip', 'broken.gz'),
                           (b'PK\x03\x04broken', 'broken.zip'),
                           (b'not an archive', 'broken.tar')]:
            with self.subTest(name=name):
                self.assertTrue(any(f['status'] == 'UNVERIFIED'
                                    for f in self.findings(data, name)))
        with patch.object(scanner, 'LIMIT', 3):
            self.assertEqual('UNVERIFIED', self.findings(b'four')[0]['status'])
        with patch.object(scanner, 'MAX_DEPTH', -1):
            self.assertEqual('UNVERIFIED', self.findings(b'x')[0]['status'])

    def test_system_paths_are_not_personal_and_custom_commands_flagged(self):
        system = b'${XOS_ROOT}/src/main.cpp /usr/bin/env /dev/null /usr/lib/qt'
        self.assertFalse(self.categories(system))
        self.assertFalse(self.categories(b'{"qemu_command":["/usr/bin/env", "python3"]}'))
        self.assertFalse(self.categories(b'{"qemu_command":["/usr/bin/qemu", "-L", "/usr/share/qemu"]}'))
        self.assertFalse(self.categories('Home/End/Delete 和 /Home/End 组合键'.encode()))
        self.assertIn('absolute_command', self.categories(b'{"qemu_command":["/opt/custom/qemu"]}'))
        self.assertIn('workspace_scratch', self.categories(b'/workspace/' + b'scratch/session/project/build.log'))
        self.assertIn('framework_python', self.categories(b'/Library/' + b'Frameworks/Python.framework/Versions/3.14/bin/python3'))

    def test_index_reads_staged_blob_not_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(*args):
                subprocess.run(['git', '-C', str(root), *args], check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            git('init', '-q')
            target = root / 'evidence.md'
            target.write_text('clean baseline\n')
            git('add', 'evidence.md')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                'commit', '-qm', 'baseline')
            target.write_bytes(b'/Users/' + b'example_dev/private')
            git('add', 'evidence.md')
            target.write_text('clean working tree copy\n')
            index = scanner.scan_repository(root, source='index', base='HEAD')
            working = scanner.scan_repository(root, source='worktree', base='HEAD')
            self.assertIn('macos_home', {f['category'] for f in index['findings']})
            self.assertEqual('PUBLIC_READY', working['status'])
            target.write_text('clean staged copy\n')
            git('add', 'evidence.md')
            target.write_bytes(b'/home/' + b'example_dev/private')
            index = scanner.scan_repository(root, source='index', base='HEAD')
            working = scanner.scan_repository(root, source='worktree', base='HEAD')
            self.assertEqual('PUBLIC_READY', index['status'])
            self.assertIn('linux_home', {f['category'] for f in working['findings']})
            missing = scanner.scan_repository(root, source='index', paths=['missing-evidence.tar.gz'])
            self.assertEqual('UNVERIFIED', missing['findings'][0]['status'])

    def test_public_serialization_uses_known_roots_and_rejects_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value = 'file=' + str(root / 'work.img') + ',format=raw'
            self.assertEqual('file=${XOS_WORK_DIR}/work.img,format=raw',
                             portable(value, [('XOS_WORK_DIR', root)], strict=True))
            with self.assertRaises(ValueError):
                portable('/Users/' + 'example_dev/private', strict=True)

    def test_identity_gate_rejects_empty_and_hides_mixed_case_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                scanner.scan_repository(Path(tmp), identities=[''])
        location = scanner.safe_location('evidence/' + 'EXAMPLE_DEV/report', ['example_dev'])
        self.assertTrue(location.startswith('path-sha256:'))
        self.assertNotIn('EXAMPLE_DEV', location)


if __name__ == '__main__':
    unittest.main()
