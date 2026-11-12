#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual compiler/ar capture, including renamed members and tampered inputs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from archive_provenance import capture_build, copy_archive_provenance, digest
from archive_member_map import verify_manifest, verify_bundle


class provenance_tests(unittest.TestCase):
    def test_discarded_compiler_probe_does_not_record_an_object(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'probe.c'
            source.write_text('int probe(void) { return 1; }\n')
            capture = capture_build(root, 'configure-discard', 'Apache-2.0')
            subprocess.run([*capture.launcher(), 'cc', '-c', str(source), '-o', os.devnull], check=True)
            self.assertEqual(list(capture.records.iterdir()), [])
            self.assertEqual(list(capture.sources.iterdir()), [])
            source.write_text('this is not a C translation unit\n')
            failure = subprocess.run([*capture.launcher(), 'cc', '-c', str(source), '-o', os.devnull],
                                     capture_output=True, text=True)
            self.assertNotEqual(failure.returncode, 0)
            self.assertEqual(list(capture.records.iterdir()), [])

    def test_compiler_launcher_and_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, target, archive = (root / name for name in ('input.c', 'renamed.o', 'libprobe.a'))
            source.write_text('int answer(void) { return 42; }\n')
            capture = capture_build(root, 'actual-build-1', 'Apache-2.0')
            subprocess.run([*capture.launcher(), 'cc', '-c', str(source), '-o', str(target)], check=True)
            subprocess.run(['ar', 'rcsD', str(archive), str(target)], check=True)
            manifest = capture.archive(archive)
            record = json.loads(manifest.read_text())
            self.assertEqual(record['members'][0]['source_name'], 'input.c')
            self.assertEqual(record['members'][0]['member'], 'renamed.o')
            self.assertEqual(verify_manifest(manifest, root, 'actual-build-1')['derived_members'], 0)
            sdk = root / 'sdk'
            sdk.mkdir()
            copied_archive = sdk / archive.name
            copied_archive.write_bytes(archive.read_bytes())
            copied = copy_archive_provenance(manifest, root, copied_archive, sdk)
            provenance = {'version': 1, 'manifests': {copied.name: digest(copied.read_bytes())}, 'legacy_archives': {}}
            self.assertTrue(verify_bundle(sdk, provenance)['all_archives_accounted'])
            (sdk / 'unregistered.a').write_bytes(archive.read_bytes())
            with self.assertRaisesRegex(ValueError, 'coverage mismatch'):
                verify_bundle(sdk, provenance)
            with self.assertRaisesRegex(ValueError, 'build_id'):
                verify_manifest(manifest, root, 'another-build')
            snapshot = root / record['members'][0]['source']
            snapshot.write_text('changed source\n')
            with self.assertRaisesRegex(ValueError, 'sha256 mismatch'):
                verify_manifest(manifest, root, 'actual-build-1')

    def test_uncaptured_and_modified_object_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, target, archive = (root / name for name in ('source.c', 'object.o', 'library.a'))
            source.write_text('int number = 1;\n')
            capture = capture_build(root, 'actual-build-2', 'Apache-2.0')
            command = ['cc', '-c', str(source), '-o', str(target)]
            subprocess.run(command, check=True)
            subprocess.run(['ar', 'rcsD', str(archive), str(target)], check=True)
            with self.assertRaisesRegex(ValueError, 'captured compilation'):
                capture.archive(archive)
            capture.record(source, target, command)
            manifest = capture.archive(archive)
            original = archive.read_bytes()
            source.write_text('int number = 2;\n')
            subprocess.run(command, check=True)
            subprocess.run(['ar', 'rcsD', str(archive), str(target)], check=True)
            with self.assertRaisesRegex(ValueError, 'captured compilation'):
                capture.archive(archive)
            with self.assertRaisesRegex(ValueError, 'sha256 mismatch'):
                verify_manifest(manifest, root, 'actual-build-2')
            archive.write_bytes(original)
            self.assertTrue(verify_manifest(manifest, root, 'actual-build-2')['content_verified'])


if __name__ == '__main__':
    unittest.main()
