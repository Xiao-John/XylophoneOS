# SPDX-License-Identifier: Apache-2.0
"""Exercise archive provenance readers against actual GNU ar output."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "scripts"))
import gcc_runtime_member_license_map as gcc_map
import newlib_member_license_map as newlib_map
import qt_member_license_map as qt_map
import archive_member_map as member_map


@unittest.skipUnless(shutil.which("ar"), "GNU ar is required")
class archive_reader_tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="xos_archive_map_")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.member = self.folder / "a.o"
        self.member.write_bytes(b"short object payload")
        self.long_member = self.folder / "long_archive_member_name.o"
        self.long_member.write_bytes(b"long object payload")
        self.archive = self.folder / "libtest.a"
        subprocess.run(["ar", "qc", str(self.archive), str(self.member),
                        str(self.long_member)], check=True, capture_output=True)

    def test_members_match_real_ar(self):
        expected = {p.name: p.read_bytes() for p in (self.member, self.long_member)}
        self.assertEqual(list(newlib_map.iter_archive_members(self.archive)), list(expected))
        for reader in (gcc_map.read_archive, qt_map.read_archive):
            with self.subTest(reader=reader.__module__):
                self.assertEqual(reader(self.archive), expected)

    def assert_rejected(self):
        for reader in (newlib_map.iter_archive_members, gcc_map.read_archive,
                       qt_map.read_archive):
            with self.subTest(reader=reader.__module__):
                with self.assertRaises((ValueError, SystemExit)):
                    list(reader(self.archive))

    def test_truncated_payload_is_rejected(self):
        self.archive.write_bytes(self.archive.read_bytes()[:-4])
        self.assert_rejected()

    def test_trailing_partial_header_is_rejected(self):
        self.archive.write_bytes(self.archive.read_bytes() + b"partial")
        self.assert_rejected()

    def test_invalid_header_trailer_is_rejected(self):
        data = bytearray(self.archive.read_bytes())
        data[66:68] = b"xx"
        self.archive.write_bytes(data)
        self.assert_rejected()

    def test_duplicate_names_cannot_be_silently_merged(self):
        subprocess.run(["ar", "q", str(self.archive), str(self.member)],
                       check=True, capture_output=True)
        actual = subprocess.check_output(["ar", "t", str(self.archive)], text=True)
        self.assertEqual(actual.splitlines().count("a.o"), 2)
        self.assert_rejected()


class qt_object_record_tests(unittest.TestCase):
    def test_retained_object_must_match_archive_payload(self):
        with tempfile.TemporaryDirectory(prefix="xos_qt_map_") as folder:
            root = Path(folder)
            source_root = root / "qtbase"
            source = source_root / "src/corelib/kernel/qobject.cpp"
            source.parent.mkdir(parents=True)
            source.write_text("// SPDX-License-Identifier: LGPL-3.0-only\n")
            obj = root / "qt6_b1_20261031/widgets/src/corelib/CMakeFiles/Core.dir/kernel/qobject.cpp.o"
            obj.parent.mkdir(parents=True)
            obj.write_bytes(b"retained object")
            objects = {obj.name: [obj]}
            matched = qt_map.resolve(obj.name, obj.read_bytes(), {}, objects,
                                     "Core", source_root, {}, [])
            self.assertEqual(matched, ("src/corelib/kernel/qobject.cpp", "object_record", False))
            mismatched = qt_map.resolve(obj.name, b"different archive object", {}, objects,
                                        "Core", source_root, {}, [])
            self.assertEqual(mismatched, (None, "object_record_byte_mismatch", False))


@unittest.skipUnless(shutil.which("ar"), "GNU ar is required")
class manifest_tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="xos_member_manifest_")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.c"
        self.source.write_text("int xos_example(void) { return 1; }\n")
        obj = self.root / "source.o"
        obj.write_bytes(b"original archive payload")
        self.archive = self.root / "libexample.a"
        subprocess.run(["ar", "qc", str(self.archive), str(obj)],
                       check=True, capture_output=True)
        self.manifest_path = self.root / "member_manifest.json"
        self.manifest = {
            "version": 1, "archive": "libexample.a",
            "archive_sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest(),
            "build_id": "audit-test-build", "generator": "build.py",
            "members": [{"member": "source.o", "source": "source.c",
                         "source_sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(),
                         "declaration_class": "spdx"}],
        }

    def verify(self):
        self.manifest_path.write_text(json.dumps(self.manifest))
        return member_map.verify_manifest(self.manifest_path, self.root, "audit-test-build")

    def test_valid_manifest_and_cli(self):
        result = self.verify()
        self.assertEqual(result["members"], 1)
        self.assertEqual(result["derived_members"], 0)
        run = subprocess.run([sys.executable, str(repo_root / "scripts/archive_member_map.py"),
                              str(self.manifest_path), "--root", str(self.root),
                              "--build-id", "audit-test-build"],
                             check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(run.stdout), result)

    def test_derived_mapping_is_reported_as_derived(self):
        self.manifest["members"][0]["derived"] = True
        self.assertEqual(self.verify()["derived_members"], 1)

    def test_changed_source_is_rejected(self):
        self.source.write_text("int xos_example(void) { return 2; }\n")
        with self.assertRaisesRegex(ValueError, "sha256 mismatch"):
            self.verify()

    def test_changed_archive_with_same_member_names_is_rejected(self):
        obj = self.root / "source.o"
        obj.write_bytes(b"replacement archive payload")
        subprocess.run(["ar", "r", str(self.archive), str(obj)],
                       check=True, capture_output=True)
        with self.assertRaisesRegex(ValueError, "sha256 mismatch"):
            self.verify()

    def test_missing_member_is_rejected(self):
        self.manifest["members"] = []
        with self.assertRaisesRegex(ValueError, "member set mismatch"):
            self.verify()

    def test_duplicate_manifest_member_is_rejected(self):
        self.manifest["members"] *= 2
        with self.assertRaisesRegex(ValueError, "duplicate manifest member"):
            self.verify()

    def test_wrong_build_is_rejected(self):
        self.manifest["build_id"] = "different-build"
        with self.assertRaisesRegex(ValueError, "build_id mismatch"):
            self.verify()

    def test_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="xos_outside_") as outside:
            target = Path(outside) / "outside.c"
            target.write_text("outside")
            (self.root / "escape").symlink_to(target)
            self.manifest["members"][0]["source"] = "escape"
            with self.assertRaisesRegex(ValueError, "escapes repository"):
                self.verify()

    def test_non_repository_path_is_rejected(self):
        for path in ("/tmp/source.c", "../source.c", ".", "C:/source.c"):
            with self.subTest(path=path):
                self.manifest["members"][0]["source"] = path
                with self.assertRaisesRegex(ValueError, "repository-relative"):
                    self.verify()


if __name__ == "__main__":
    unittest.main()
