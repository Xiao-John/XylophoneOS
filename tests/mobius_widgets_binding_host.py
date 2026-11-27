#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the Widgets receipt binding without rebuilding the target prefix."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/ports/aurora_desktop/glibc"))

import widgets_kit
from xypm_format import canonical, load_json


class WidgetsBinding(unittest.TestCase):
    def test_target_receipt_binds_actual_inputs(self):
        qt = load_json(widgets_kit.QT / "source_lock.json")
        binding = {"qt_version": qt["version"], "qtbase_prepared_tree_sha256": "1" * 64,
                   "qt_build_cache_sha256": "2" * 64, "sdk_manifest_sha256": "3" * 64,
                   "sdk_profile_file_sha256": "4" * 64}
        generators = {name: "5" * 64 for name in widgets_kit.WIDGETS_GENERATORS}
        target = "6" * 64
        tools = {"g++": "7" * 64}
        files = {"target_tree_sha256": target, "qt_inputs": generators}
        manifest = binding | {"format_version": 1, "kind": "mobius_widgets",
                              "qtbase_archive_sha256": qt["sha256"], "target_tools": tools, "files": files}
        receipt = binding | {"status": "static_qt_widgets_target_installed",
                             "qtbase_features": {"widgets": "ON", "filedialog": "OFF"},
                             "sources": {"qtbase": qt["sha256"]}, "cross_tools": tools,
                             "target_tree_sha256": target, "native_generators": generators}
        with TemporaryDirectory() as temporary:
            kit = Path(temporary)
            manifest_path = kit / "manifest.json"
            target_path = kit / widgets_kit.TARGET_RECEIPT
            manifest_path.write_bytes(canonical(manifest))
            with patch.object(widgets_kit, "fingerprint", return_value=files):
                sdk = binding["sdk_manifest_sha256"]
                profile = binding["sdk_profile_file_sha256"]
                legacy_digest = widgets_kit.sha(manifest_path)
                self.assertEqual(widgets_kit.verify_kit(kit, legacy_digest, sdk, profile), legacy_digest)
                with self.assertRaisesRegex(ValueError, "requires the installed target build receipt"):
                    widgets_kit.verify_kit(kit, legacy_digest, sdk, profile, profile_id=widgets_kit.UNIFIED_V2)
                target_path.write_bytes(canonical(receipt))
                manifest["target_receipt_sha256"] = widgets_kit.sha(target_path)
                manifest_path.write_bytes(canonical(manifest))
                digest = widgets_kit.sha(manifest_path)
                self.assertEqual(widgets_kit.verify_kit(kit, digest, sdk, profile, profile_id=widgets_kit.UNIFIED_V2),
                                 digest)
            for field, replacement in (
                ("status", "static_qt_quick_target_installed"),
                ("qtbase_features", {"widgets": "OFF", "filedialog": "OFF"}),
                ("sdk_manifest_sha256", "a" * 64),
                ("sdk_profile_file_sha256", "a" * 64),
                ("target_tree_sha256", "a" * 64),
                ("native_generators", generators | {"uic": "a" * 64}),
            ):
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Widgets"):
                    target_path.write_bytes(canonical(receipt | {field: replacement}))
                    widgets_kit.verify_target_receipt(target_path, manifest)


if __name__ == "__main__":
    unittest.main()
