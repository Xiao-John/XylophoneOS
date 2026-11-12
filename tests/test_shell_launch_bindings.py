# SPDX-License-Identifier: Apache-2.0
"""Exercise real SL3/SL4 receipt binding and serial-result admission."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from shell_launch_support import bind_system, bind_tool, check_result, sha


class shell_launch_binding_tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="xos_native_binding_")
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.system = self.workspace / "build/system"
        self.sdk = self.system / "sdk"
        names = ("manifest.json", "crt0_posix.o", "user.ld", "include/test.h",
                 "lib/libxos.a", "lib/libxos_loader.a", "lib/libc.a", "lib/libm.a")
        for name in names:
            path = self.sdk / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(name)
        (self.sdk / "manifest.json").write_text(json.dumps({"build_id": "fixture", "archive_provenance": {"retained": True}}))
        self.source = self.workspace / "src/program.cpp"
        self.source.parent.mkdir()
        self.source.write_text("int entry;\n")
        (self.system / "xos-install.iso").write_bytes(b"bound fixture ISO")
        self.manifest = {"build_id": "fixture", "sources": {"src/program.cpp": sha(self.source)},
                         "artifacts": {str(path.relative_to(self.system)): {"sha256": sha(path)}
                                       for path in self.system.rglob("*") if path.is_file()}}
        (self.system / "manifest.json").write_text(json.dumps(self.manifest))
        self.artifact = self.workspace / "tools/dash"
        self.artifact.parent.mkdir()
        self.artifact.write_bytes(b"receipt-selected fixture executable")
        self.receipt = self.workspace / "tools/receipt.json"
        self.data = {"profile": "dash_c3", "status": "built_not_run", "elf": "tools/dash",
                     "sha256": sha(self.artifact), "inputs": {"sdk/" + str(path.relative_to(self.sdk)): sha(path)
                                                            for path in self.sdk.rglob("*") if path.is_file()}}
        self.data["inputs"]["src/program.cpp"] = sha(self.source)
        self.save_receipt()

    def save_receipt(self):
        self.receipt.write_text(json.dumps(self.data))

    def bind(self):
        return bind_tool(self.receipt, "dash_c3", self.sdk, self.workspace)

    def test_system_binds_sources_iso_and_full_sdk(self):
        self.assertEqual(bind_system(self.system, self.workspace)["build_id"], "fixture")

    def test_changed_source_rejected(self):
        self.source.write_text("changed")
        with self.assertRaises(ValueError): bind_system(self.system, self.workspace)

    def test_changed_iso_rejected(self):
        (self.system / "xos-install.iso").write_bytes(b"different")
        with self.assertRaises(ValueError): bind_system(self.system, self.workspace)

    def test_unbound_sdk_addition_rejected(self):
        (self.sdk / "include/extra.h").write_text("unbound")
        with self.assertRaises(ValueError): bind_system(self.system, self.workspace)

    def test_explicit_receipt_beats_newer_cache_artifact(self):
        newer = self.workspace / "tools/newer_dash"
        newer.write_bytes(b"unbound")
        os.utime(self.artifact, (1, 1))
        os.utime(newer, (200, 200))
        selected, binding = self.bind()
        self.assertEqual(selected, self.artifact)
        self.assertEqual(binding["receipt_sha256"], sha(self.receipt))

    def test_receipt_does_not_rewrite_sdk_provenance(self):
        original = (self.sdk / "manifest.json").read_bytes()
        self.bind()
        self.assertEqual((self.sdk / "manifest.json").read_bytes(), original)

    def test_changed_tool_elf_rejected(self):
        self.artifact.write_bytes(b"changed")
        with self.assertRaises(ValueError): self.bind()

    def test_changed_sdk_header_rejected_even_when_manifest_unchanged(self):
        (self.sdk / "include/test.h").write_text("different header")
        with self.assertRaises(ValueError): self.bind()

    def test_tool_source_mismatch_rejected(self):
        self.source.write_text("different source")
        with self.assertRaises(ValueError): self.bind()

    def test_wrong_profile_rejected(self):
        self.data["profile"] = "another_profile"
        self.save_receipt()
        with self.assertRaises(ValueError): self.bind()

    def test_incomplete_sdk_receipt_rejected(self):
        del self.data["inputs"]["sdk/manifest.json"]
        self.save_receipt()
        with self.assertRaises(ValueError): self.bind()

    def test_missing_artifact_is_not_execution(self):
        self.artifact.unlink()
        with self.assertRaises(FileNotFoundError): self.bind()

    def test_escaping_receipt_path_rejected(self):
        self.data["elf"] = "../outside"
        self.save_receipt()
        with self.assertRaises(ValueError): self.bind()

    def test_zero_exit_cannot_pass_negative_case(self):
        with self.assertRaises(AssertionError): check_result(b"kind=exited code=0\n", None)
        self.assertEqual(check_result(b"kind=exited code=1\n", None), 1)

    def test_missing_final_exit_rejected(self):
        with self.assertRaises(AssertionError): check_result(b"RESULT_OK\n", 0, [b"RESULT_OK"])

    def test_echoed_marker_does_not_pass(self):
        with self.assertRaises(AssertionError):
            check_result(b"xsh> printf RESULT_OK\r\nkind=exited code=0\r\n", 0, [b"RESULT_OK"])

    def test_real_lf_and_crlf_result_lines(self):
        for ending in (b"\n", b"\r\n"):
            self.assertEqual(check_result(ending.join([b"RESULT_OK", b"kind=exited code=0", b""]), 0, [b"RESULT_OK"]), 0)

    def test_final_exit_wins_over_earlier_child(self):
        with self.assertRaises(AssertionError):
            check_result(b"kind=exited code=0\nkind=exited code=7\n", 0)
        self.assertEqual(check_result(b"kind=exited code=7\nkind=exited code=0\n", 0), 0)


if __name__ == "__main__":
    unittest.main()
