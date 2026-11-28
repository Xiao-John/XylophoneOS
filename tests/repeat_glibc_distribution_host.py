#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reject malformed received archives and invalid repeat-publication inputs."""
import io
import json
from contextlib import redirect_stdout
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

    def completed_reports(self):
        """Synthetic files with the real completed make-output envelope depth."""
        result = []
        for number in range(2):
            directory = self.root / str(number)
            (directory / 'frozen').mkdir(parents=True)
            (directory / 'frozen/program.elf').write_bytes(b'host-only immutable fixture')
            (directory / 'frozen/package_smoke_report.json').write_text(str(number))
            for name in ('runner.tar', 'system_source.tar'):
                (directory / name).write_bytes(b'host-only frozen source fixture')
            qualified = {'status': 'passed', 'release_manifest_sha256': 'a' * 64,
                'sdk_bindings': {'fixture': True},
                'system_rebuild': {'build_id': 'host_comparison_fixture'},
                'receivers': {'programs': 17, 'fixture': True},
                'guest_reports': {'reports': {'make': {'original': {'cases': {
                    'version': {'output': ['host-only make output fixture']}}}}}},
                'frozen_assets': {path.name: repeat.file_record(path)
                                  for path in (directory / 'frozen').iterdir()}}
            (directory / 'qualification.json').write_bytes(repeat.canonical(qualified))
            run = {'format': 'xos_r1_repeat_v1', 'status': 'passed', 'output_was_absent': True,
                'run_id': str(number) * 32, 'qualification': qualified,
                'qualification_sha256': repeat.sha_file(directory / 'qualification.json'),
                'bundle': {'fixture': True}, 'runner_commit': 'host_comparison_fixture',
                'runner_sha256': 'b' * 64, 'lock_sha256': 'c' * 64,
                'sdk_launcher_sha256': 'd' * 64, 'system_source_commit': 'host_source_fixture',
                'source_archives': {name: repeat.file_record(directory / name)
                                    for name in ('runner.tar', 'system_source.tar')},
                'entry_gate': {'fixture': True}, 'frozen_sdk_archive': {'fixture': True}}
            (directory / 'run.json').write_bytes(repeat.canonical(run))
            result.append(directory)
        return result

    def test_completed_report_depth_is_not_package_metadata(self):
        path = self.completed_reports()[0] / 'run.json'
        with self.assertRaisesRegex(ValueError, 'nesting exceeds 8'):
            repeat.load_json(path)
        self.assertEqual(repeat.read_run_report(path), json.loads(path.read_bytes()))

    def test_run_report_reader_rejects_invalid_envelopes(self):
        nested = 0
        for _ in range(17):
            nested = [nested]
        cases = {
            'duplicate': (b'{"format":"xos_r1_repeat_v1","run_id":1,"run_id":2}', 'duplicate'),
            'deep': (repeat.canonical({'format': 'xos_r1_repeat_v1', 'nested': nested}), 'exceeds 16'),
            'large': (b' ' * (1024 * 1024 + 1), 'exceeds 1 MiB'),
            'float': (b'{"format":"xos_r1_repeat_v1","value":1.5}', 'non-integer'),
            'nonfinite': (b'{"format":"xos_r1_repeat_v1","value":NaN}', 'non-integer'),
            'utf8': (b'\xff', 'invalid run-report'),
            'format': (b'{"format":"other"}', 'unexpected run-report format'),
        }
        for name, (data, error) in cases.items():
            with self.subTest(case=name):
                path = self.root / (name + '.json')
                path.write_bytes(data)
                with self.assertRaisesRegex(ValueError, error):
                    repeat.read_run_report(path)

    def test_compare_accepts_complete_depth_nine_reports(self):
        paths = self.completed_reports()
        output = self.root / 'comparison.json'
        with redirect_stdout(io.StringIO()):
            repeat.compare(paths, output)
        result = repeat.load_json(output)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['run_ids'], ['0' * 32, '1' * 32])
        self.assertEqual(result['run_reports'], [repeat.file_record(path / 'run.json') for path in paths])
        self.assertEqual(result['immutable_frozen_files_compared'], 1)
        for item in result['frozen_inventories']:
            self.assertTrue(item['exact_inventory_and_every_file_verified'])
            self.assertEqual(item['canonical_inventory_sha256'],
                             repeat.hashlib.sha256(repeat.canonical(item['files'])).hexdigest())

    def test_compare_rejects_unrecorded_frozen_file(self):
        paths = self.completed_reports()
        (paths[1] / 'frozen/unrecorded').write_bytes(b'not part of qualification')
        output = self.root / 'comparison.json'
        with self.assertRaisesRegex(ValueError, 'frozen directory inventory differs'):
            repeat.compare(paths, output)
        self.assertFalse(output.exists())

    def test_compare_rejects_inconsistent_input(self):
        paths = self.completed_reports()
        path = paths[1] / 'run.json'
        value = repeat.read_run_report(path)
        value['lock_sha256'] = 'e' * 64
        path.write_bytes(repeat.canonical(value))
        output = self.root / 'comparison.json'
        with self.assertRaisesRegex(ValueError, 'input differs: lock_sha256'):
            repeat.compare(paths, output)
        self.assertFalse(output.exists())

    def test_compare_rejects_changed_recorded_immutable_asset(self):
        paths = self.completed_reports()
        directory = paths[1]
        (directory / 'frozen/program.elf').write_bytes(b'different independently recorded result')
        qualified = repeat.load_json(directory / 'qualification.json')
        qualified['frozen_assets']['program.elf'] = repeat.file_record(directory / 'frozen/program.elf')
        (directory / 'qualification.json').write_bytes(repeat.canonical(qualified))
        run = repeat.read_run_report(directory / 'run.json')
        run['qualification'] = qualified
        run['qualification_sha256'] = repeat.sha_file(directory / 'qualification.json')
        (directory / 'run.json').write_bytes(repeat.canonical(run))
        output = self.root / 'comparison.json'
        with self.assertRaisesRegex(ValueError, 'immutable frozen asset differs'):
            repeat.compare(paths, output)
        self.assertFalse(output.exists())

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
