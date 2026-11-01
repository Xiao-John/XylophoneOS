#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_evidence_index as verifier


class verify_evidence_index_tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report = self.root / "report"
        self.report.mkdir()
        self.data = b"original evidence\n"
        (self.report / "evidence.txt").write_bytes(self.data)
        self.sha = hashlib.sha256(self.data).hexdigest()

    def index(self, value, name="index.json"):
        (self.report / name).write_text(json.dumps(value))
        return "report/" + name

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args],
                                       stderr=subprocess.PIPE, text=True).strip()

    def test_valid_json_and_evidence_sha256(self):
        for obj in ({"evidence.txt": self.sha}, {"files": {"evidence.txt": self.sha}},
                    {"evidence_sha256": {"evidence.txt": self.sha}},
                    {"files": {"evidence.txt": {"sha256": self.sha, "bytes": len(self.data)}}}):
            result = verifier.verify(self.root, self.index(obj))
            self.assertEqual((result["status"], result["matched"]), ("PASS", 1))

    def test_size_mismatch_and_invalid_size_fail(self):
        index = self.index({"files": {"evidence.txt": {"sha256": self.sha, "bytes": len(self.data) + 1}}})
        result = verifier.verify(self.root, index)
        self.assertEqual(result["failures"][0]["status"], "SIZE_MISMATCH")
        index = self.index({"files": {"evidence.txt": {"sha256": self.sha, "bytes": True}}})
        with self.assertRaises(ValueError):
            verifier.verify(self.root, index)

    def test_mismatch_and_missing_do_not_pass(self):
        index = self.index({"evidence.txt": self.sha, "missing.txt": self.sha})
        (self.report / "evidence.txt").write_bytes(b"modified\n")
        result = verifier.verify(self.root, index)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual({entry["status"] for entry in result["failures"]}, {"MISSING", "MISMATCH"})

    def test_sha256sums(self):
        (self.report / "PACKAGE_SHA256SUMS").write_text(self.sha + "  evidence.txt\n")
        self.assertEqual(verifier.verify(self.root, "report/PACKAGE_SHA256SUMS")["status"], "PASS")

    def test_empty_malformed_and_duplicate_indexes_fail_closed(self):
        for obj in ({}, {"evidence.txt": "bad"}, {"../outside": self.sha},
                    {"/absolute": self.sha}, {"evidence.txt": self.sha.upper()}):
            with self.subTest(obj=obj), self.assertRaises(ValueError):
                verifier.verify(self.root, self.index(obj))
        (self.report / "index.json").write_text('{"evidence.txt":"' + self.sha + '","evidence.txt":"' + self.sha + '"}')
        with self.assertRaises(ValueError):
            verifier.verify(self.root, "report/index.json")

    def test_historical_commit_is_independent_of_changed_checkout(self):
        self.git("init", "-q")
        index = self.index({"evidence.txt": self.sha})
        self.git("add", "report")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "evidence")
        revision = self.git("rev-parse", "HEAD")
        (self.report / "evidence.txt").write_bytes(b"sanitized\n")
        self.assertEqual(verifier.verify(self.root, index)["status"], "FAIL")
        original = verifier.verify(self.root, index, revision)
        self.assertEqual((original["status"], original["revision"]), ("PASS", revision))

    def test_symlinks_are_rejected(self):
        (self.report / "link.txt").symlink_to("evidence.txt")
        index = self.index({"link.txt": self.sha})
        with self.assertRaises(ValueError):
            verifier.verify(self.root, index)
        self.git("init", "-q")
        self.git("add", "report")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "symlink")
        with self.assertRaises(ValueError):
            verifier.verify(self.root, index, "HEAD")

    def test_cli_error_does_not_expose_checkout_path(self):
        result = subprocess.run([sys.executable, str(Path(verifier.__file__)), "--root", str(self.root),
                                 "missing/index.json"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "ERROR")
        self.assertNotIn(str(self.root), result.stdout)


if __name__ == "__main__":
    unittest.main()
