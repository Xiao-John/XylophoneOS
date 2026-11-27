#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Host regression for the portable Mobius package recipe digest."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from mobius_build_receipt import packaged_build_binding


def receiver_receipt(root):
    source = f"{root}/checkout"
    locations = {"source": source, "build": f"{source}/build/mobius", "sdk": f"{root}/sdk",
                 "widgets": f"{root}/qt", "profile": f"{root}/sdk/selected.json",
                 **{tool: f"{root}/tools/x86_64-elf-{tool}" for tool in ("gcc", "g++", "ar", "ranlib")}}
    return {
        "widgets_kit_manifest_sha256": "1" * 64,
        "commands": [["cmake", "-S", f"{source}/port", "-B", locations["build"],
                      f'-DXOS_QT_PREFIX={locations["widgets"]}/target',
                      f'-DXOS_GLIBC_CXX={locations["g++"]}'],
                     ["cmake", "--build", locations["build"], "--parallel", "1"]],
        "inputs": {f"{source}/port/main.cpp": "2" * 64, f'{locations["sdk"]}/manifest.json': "3" * 64,
                   f'{locations["widgets"]}/manifest.json': "1" * 64, locations["profile"]: "4" * 64},
        "relocation_paths": locations,
    }


class receipt_tests(unittest.TestCase):
    def test_relocated_recipe(self):
        first = receiver_receipt("/a")
        second = receiver_receipt("/longer/b")
        expected = packaged_build_binding(first, "a" * 64)
        self.assertEqual(expected, packaged_build_binding(second, "b" * 64))
        second["commands"][1][-1] = "2"
        self.assertNotEqual(expected, packaged_build_binding(second, "b" * 64))
        second["commands"][1][-1] = "1"
        second["inputs"][second["relocation_paths"]["profile"]] = "f" * 64
        self.assertNotEqual(expected, packaged_build_binding(second, "b" * 64))

    def test_unknown_absolute_path_rejected(self):
        receipt = receiver_receipt("/a")
        receipt["commands"][0].append("-DCMAKE_PREFIX_PATH=/a/qt-other")
        with self.assertRaisesRegex(ValueError, "no recipe root"):
            packaged_build_binding(receipt, "a" * 64)

    def test_original_receipt_digest(self):
        digest = "a" * 64
        self.assertEqual(packaged_build_binding({}, digest), {"build_receipt_sha256": digest})


if __name__ == "__main__":
    unittest.main()
