# SPDX-License-Identifier: Apache-2.0
"""Host-side checks for actionable XYPm profile mismatch diagnostics."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts')]

from xypm_format import PackageError, check_profile
from xypm_image import profile_file_for


class ProfileErrorTests(unittest.TestCase):
    def test_local_profile_cannot_satisfy_b2_package(self):
        manifest = {'target_profile': 'xos-x86_64-static-single-b2-v1', 'required_features': []}
        profile = {'id': 'xos-x86_64-sdk-local', 'features': []}
        with self.assertRaises(PackageError) as caught:
            check_profile(manifest, profile)
        message = str(caught.exception)
        self.assertIn('xos-x86_64-static-single-b2-v1', message)
        self.assertIn('xos-x86_64-sdk-local', message)
        self.assertIn('config/package/xos_x86_64_static_single_b2_v1.json', message)
        self.assertIn('development-only', message)

    def test_profile_hint_is_resolved_from_config(self):
        self.assertEqual(profile_file_for('xos-x86_64-static-single-b2-v1'),
                         'config/package/xos_x86_64_static_single_b2_v1.json')
        self.assertIsNone(profile_file_for('not-a-real-profile'))

    def test_feature_mismatch_is_separate_from_profile_mismatch(self):
        manifest = {'target_profile': 'xos-x86_64-static-single-b2-v1',
                    'required_features': ['threads']}
        profile = {'id': 'xos-x86_64-static-single-b2-v1', 'features': []}
        with self.assertRaises(PackageError) as caught:
            check_profile(manifest, profile)
        self.assertIn('required feature unavailable', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
