#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reject mixed SDKs, changed headers, traversal and unrecorded aliases."""
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/ports/webkit'))
from target_inputs import recheck_inputs, target_inputs


class target_inputs_tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.target = Path(self.temporary.name)
        files = {'prefix/include/api.h': b'int api(void);\n', 'prefix/lib/libapi.a': b'archive'}
        for name, data in files.items():
            path = self.target / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        self.record = {'status': 'built', 'profile_binding': {'sdk_tree_sha256': 'a' * 64},
                       'artifacts': {name: sha256(data).hexdigest() for name, data in files.items()}}
        self.save()

    def save(self):
        (self.target / 'manifest.json').write_text(json.dumps(self.record))

    def inspect(self):
        return target_inputs(self.target, 'built', 'a' * 64)

    def test_end_of_build_tamper(self):
        _, inputs = self.inspect(); recheck_inputs(inputs)
        (self.target / 'prefix/include/api.h').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'changed during build'): recheck_inputs(inputs)

    def test_wrong_sdk(self):
        with self.assertRaisesRegex(ValueError, 'another SDK'): target_inputs(self.target, 'built', 'b' * 64)

    def test_changed_header(self):
        (self.target / 'prefix/include/api.h').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'artifact differs'): self.inspect()

    def test_unrecorded_header(self):
        (self.target / 'prefix/include/extra.h').write_text('unexpected')
        with self.assertRaisesRegex(ValueError, 'not completely bound'): self.inspect()

    def test_traversal(self):
        self.record['artifacts']['../outside'] = 'a' * 64; self.save()
        with self.assertRaisesRegex(ValueError, 'noncanonical'): self.inspect()

    def test_header_symlink(self):
        path = self.target / 'prefix/include/api.h'; path.rename(path.with_suffix('.real')); path.symlink_to('api.real')
        with self.assertRaisesRegex(ValueError, 'symlink'): self.inspect()

    def test_recorded_metadata_alias(self):
        original = self.target / 'prefix/lib/versioned.inc'; original.write_text('ICU_VERSION=79\n')
        alias = self.target / 'prefix/lib/current.inc'; alias.symlink_to(original.name)
        for path in (original, alias): self.record['artifacts'][path.relative_to(self.target).as_posix()] = sha256(original.read_bytes()).hexdigest()
        self.save(); _, inputs = self.inspect(); recheck_inputs(inputs)
        original.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'changed during build'): recheck_inputs(inputs)

    def test_alias_to_unrecorded_target(self):
        original = self.target / 'prefix/lib/unrecorded.inc'; original.write_text('not in receipt')
        alias = self.target / 'prefix/lib/current.inc'; alias.symlink_to(original.name)
        self.record['artifacts'][alias.relative_to(self.target).as_posix()] = sha256(original.read_bytes()).hexdigest(); self.save()
        with self.assertRaisesRegex(ValueError, 'symlink'): self.inspect()


if __name__ == '__main__': unittest.main()
