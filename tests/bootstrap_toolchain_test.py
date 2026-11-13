#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real bundle round trips; executable/version qualification is a separate gate."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / 'scripts'))
import bootstrap_toolchain


class bootstrap_tests(unittest.TestCase):
    def test_regular_file_modes_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, restored = root / 'original', root / 'restored'
            source.mkdir()
            for name, mode in (('readonly', 0o444), ('group_writable', 0o664), ('executable', 0o555)):
                path = source / name
                path.write_text(name + '\n')
                path.chmod(mode)
            (source / 'link').symlink_to('readonly')
            expected = bootstrap_toolchain.inventory(source)
            bundle = root / 'toolchain.tar.xz'
            # Only the unrelated pinned-tool executable audit is replaced.
            # Export, tar filtering, hashes, inventories, chmod and rename are real.
            with patch.object(bootstrap_toolchain, 'check_tools', return_value={}) as check_tools:
                with contextlib.redirect_stdout(io.StringIO()):
                    bootstrap_toolchain.export_bundle(source, bundle)
                    bootstrap_toolchain.restore_bundle(bundle, bootstrap_toolchain.sha(bundle), restored)
                self.assertEqual(check_tools.call_count, 3)
            actual = bootstrap_toolchain.inventory(restored)
            actual.pop('activate.sh')
            actual.pop('receipt.json')
            self.assertEqual(actual, expected)
            self.assertEqual((restored / 'link').read_text(), 'readonly\n')


if __name__ == '__main__':
    unittest.main()
