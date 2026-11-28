#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reject malformed received archives and invalid repeat-publication inputs."""
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import repeat_glibc_distribution as repeat


class repeat_cases(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def archive(self, entries):
        path = self.root / 'input.tar'
        with tarfile.open(path, 'w') as archive:
            for name, kind in entries:
                member = tarfile.TarInfo(name)
                if kind == 'file':
                    member.size = 3
                    archive.addfile(member, io.BytesIO(b'abc'))
                else:
                    member.type = kind
                    member.linkname = 'outside'
                    archive.addfile(member)
        return path

    def test_traversal(self):
        with self.assertRaisesRegex(ValueError, 'unsafe archive path'):
            repeat.safe_extract(self.archive([('../escape', 'file')]), self.root / 'out')

    def test_absolute_path(self):
        with self.assertRaisesRegex(ValueError, 'unsafe archive path'):
            repeat.safe_extract(self.archive([('/escape', 'file')]), self.root / 'out')

    def test_duplicate(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            repeat.safe_extract(self.archive([('a', 'file'), ('a', 'file')]), self.root / 'out')

    def test_symlink(self):
        with self.assertRaisesRegex(ValueError, 'nonregular'):
            repeat.safe_extract(self.archive([('a', tarfile.SYMTYPE)]), self.root / 'out')

    def test_hardlink(self):
        with self.assertRaisesRegex(ValueError, 'nonregular'):
            repeat.safe_extract(self.archive([('a', tarfile.LNKTYPE)]), self.root / 'out')

    def test_wrong_root(self):
        with self.assertRaisesRegex(ValueError, 'archive root differs'):
            repeat.safe_extract(self.archive([('wrong/a', 'file')]), self.root / 'out', strip='right')

    def test_no_overwrite(self):
        output = self.root / 'out'
        output.mkdir()
        (output / 'kept').write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            repeat.safe_extract(self.archive([('a', 'file')]), output)
        self.assertEqual((output / 'kept').read_bytes(), b'keep')

    def test_wrong_digest(self):
        source = self.root / 'input'
        source.write_bytes(b'input')
        with self.assertRaisesRegex(ValueError, 'identity differs'):
            repeat.checked_file(source, {'bytes': 5, 'sha256': '0' * 64})

    def test_source_absent(self):
        with self.assertRaisesRegex(ValueError, 'missing regular input'):
            repeat.checked_file(self.root / 'missing', {'bytes': 0, 'sha256': '0' * 64})

    def test_checksums_duplicate(self):
        source = self.root / 'input'
        source.write_bytes(b'input')
        line = repeat.sha_file(source) + '  input\n'
        (self.root / 'SUMS').write_text(line + line)
        with self.assertRaisesRegex(ValueError, 'duplicate checksum'):
            repeat.verify_checksums(self.root, 'SUMS', 2)

    def test_first_gate_is_exact(self):
        lock = repeat.load_json(repeat.LOCK)
        result = repeat.entry_gate(lock)
        self.assertEqual(set(result), {'first_qualification', 'delivery_receipt'})
        lock['first_qualification']['artifact']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'identity differs'):
            repeat.entry_gate(lock)

    def test_single_run_cannot_qualify(self):
        with self.assertRaisesRegex(ValueError, 'at least two'):
            repeat.compare([self.root], self.root / 'comparison.json')
        self.assertFalse((self.root / 'comparison.json').exists())

    def retirement_inputs(self, status='passed'):
        disk = self.root / 'guest.img'
        disk.write_bytes(b'completed guest media\0' * 100)
        (self.root / 'producer.json').write_bytes(repeat.canonical({'status': 'passed_subset'}))
        (self.root / 'consumer.json').write_bytes(repeat.canonical({'status': status}))
        return disk, repeat.file_record(disk)

    def test_retirement_waits_for_successful_consumer(self):
        disk, record = self.retirement_inputs('running')
        with self.assertRaisesRegex(ValueError, 'did not complete'):
            repeat.retire_guest_disk(self.root, 'guest.img', 'producer.json',
                                     record['sha256'], 'consumer.json')
        self.assertEqual(repeat.file_record(disk), record)
        self.assertFalse((self.root / 'guest_disk_retirement.json').exists())

    def test_retirement_rejects_changed_media(self):
        disk, record = self.retirement_inputs()
        with self.assertRaisesRegex(ValueError, 'changed before retirement'):
            repeat.retire_guest_disk(self.root, 'guest.img', 'producer.json',
                                     '0' * 64, 'consumer.json')
        self.assertEqual(repeat.file_record(disk), record)
        self.assertFalse((self.root / 'guest_disk_retirement.json').exists())

    def test_retirement_preserves_complete_identity(self):
        disk, record = self.retirement_inputs()
        repeat.retire_guest_disk(self.root, 'guest.img', 'producer.json',
                                 record['sha256'], 'consumer.json')
        self.assertFalse(disk.exists())
        item, = repeat.load_json(self.root / 'guest_disk_retirement.json')['records']
        self.assertEqual(item['artifact'], record)
        self.assertEqual(item['producer_report']['sha256'], repeat.sha_file(self.root / 'producer.json'))
        self.assertEqual(item['last_consumer_report']['sha256'], repeat.sha_file(self.root / 'consumer.json'))
        self.assertEqual(item['status'], 'removed_after_complete_hash_verification')


if __name__ == '__main__':
    unittest.main()
