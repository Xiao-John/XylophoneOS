#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Deterministic host-only cases for the read-only GCC Seed preflight."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("seed_preflight", ROOT / "scripts/seed_preflight.py")
seed_preflight = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = seed_preflight
SPEC.loader.exec_module(seed_preflight)


def make_elf(*, load_flags: int = 5, load_address: int = 0x40000000,
             entry: int | None = None, interpreter: bool = False,
             dynamic: bool = False, tls: tuple[int, int, int, int, int] | None = None,
             loads: int = 1) -> bytes:
    """Build a tiny ELF64 AMD64 ET_EXEC with deterministic program headers."""
    phdrs = []
    if interpreter:
        phdrs.append((3, 4, 0x300, 0, 0, 8, 8, 1))
    if dynamic:
        phdrs.append((2, 6, 0x300, 0x40000300, 0, 16, 16, 8))
    for index in range(loads):
        address = load_address if index == 0 else load_address + index * 0x1000
        phdrs.append((1, load_flags, 0x1000 + index * 0x1000, address, 0,
                      4, 0x1000, 0x1000))
    if tls is not None:
        off, address, filesz, memsz, alignment = tls
        phdrs.append((7, 6, off, address, 0, filesz, memsz, alignment))
    header = bytearray(64)
    header[:16] = b"\x7fELF" + bytes((2, 1, 1, 0, 0)) + bytes(7)
    struct.pack_into("<HHI", header, 16, 2, 62, 1)
    struct.pack_into("<QQ", header, 24, entry if entry is not None else load_address, 64)
    struct.pack_into("<I", header, 48, 0)
    struct.pack_into("<HHH", header, 52, 64, 56, len(phdrs))
    data = bytearray(max(0x2000 + (loads - 1) * 0x1000, 64 + len(phdrs) * 56))
    data[:64] = header
    for index, phdr in enumerate(phdrs):
        struct.pack_into("<IIQQQQQQ", data, 64 + index * 56, *phdr)
    for index in range(loads):
        data[0x1000 + index * 0x1000:0x1004 + index * 0x1000] = b"\x90\x90\x90\xc3"
    if tls is not None and tls[2]:
        off, _address, _filesz, _memsz, _alignment = tls
        data[off:off + tls[2]] = b"\x12" * tls[2]
    return bytes(data)


class SeedPreflightCases(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.seed_root = self.root / "seed"
        self.sysroot_root = self.root / "sysroot"
        self.seed_root.mkdir()
        self.sysroot_root.mkdir()
        tool_data = make_elf()
        (self.sysroot_root / "include").mkdir()
        (self.sysroot_root / "include/api.h").write_text("int xos_api;\n")
        self.tools = {}
        self.install = []
        for name in ("gcc", "as", "ld", "ar", "ranlib"):
            guest = f"/usr/bin/x86_64-elf-{name}"
            source_path = f"tools/{name}"
            target = self.seed_root / source_path
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(tool_data)
            row = {"path": source_path, "guest_path": guest,
                   "sha256": hashlib.sha256(tool_data).hexdigest(), "bytes": len(tool_data)}
            self.install.append(row)
            self.tools[name] = dict(row)
        hdr = b"int xos_api;\n"
        self.sys_files = [{"path": "include/api.h", "guest_path": "/sysroot/include/api.h",
                           "sha256": hashlib.sha256(hdr).hexdigest(), "bytes": len(hdr)}]
        sdk_data = json.dumps({"files": []}, sort_keys=True).encode()
        (self.seed_root / "sdk").mkdir()
        (self.seed_root / "sdk/manifest.json").write_bytes(sdk_data)
        self.seed = {"manifest_schema": 2, "install_files": self.install,
                     "tools": self.tools,
                     "sdk_manifest": {"path": "sdk/manifest.json",
                                      "sha256": hashlib.sha256(sdk_data).hexdigest()}}
        self.sysroot = {"files": self.sys_files}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def check(self, seed=None, sysroot=None, **kwargs):
        return seed_preflight.validate_bundle(
            self.seed if seed is None else seed, self.seed_root,
            self.sysroot if sysroot is None else sysroot, self.sysroot_root,
            required_tools=("gcc", "as", "ld", "ar", "ranlib"), **kwargs)

    def codes(self, report):
        return {item["code"] for item in report.diagnostics}

    def test_valid_explicit_bundle_and_sysroot_prefix(self):
        result = self.check()
        self.assertTrue(result.ok, result.diagnostics)
        self.assertEqual(result.sysroot_files[0]["guest_path"], "/sysroot/include/api.h")
        self.assertTrue(result.to_dict()["not_guest_test"])

    def test_source_host_absolute_and_parent_paths_rejected(self):
        for bad in (str(self.seed_root / "tool.elf"), "../seed/tool.elf", "C:/host/tool"):
            seed = json.loads(json.dumps(self.seed))
            seed["install_files"][0]["path"] = bad
            result = self.check(seed=seed)
            self.assertTrue({"source_path", "tool_host_path"} & self.codes(result), bad)

    def test_symlink_in_parent_is_rejected(self):
        real = self.seed_root / "real"
        real.mkdir()
        (real / "tool.elf").write_bytes((self.seed_root / "tools/gcc").read_bytes())
        (self.seed_root / "alias").symlink_to(real, target_is_directory=True)
        seed = json.loads(json.dumps(self.seed))
        seed["install_files"][0]["path"] = "alias/tool.elf"
        result = self.check(seed=seed)
        self.assertIn("source_file", self.codes(result))

    def test_isolated_project_root_is_never_read(self):
        isolated = self.seed_root / "localpilot"
        isolated.mkdir()
        (isolated / "sentinel").write_text("must not be opened")
        seed = json.loads(json.dumps(self.seed))
        seed["install_files"][0]["path"] = "localpilot/sentinel"
        result = self.check(seed=seed)
        self.assertIn("source_isolated_project", self.codes(result))

    def test_guest_path_canonical_and_ascii_rules(self):
        for bad in ("relative", "/usr//bin/x", "/usr/../bin/x", "/usr/./x", "/usr/x/", "/usr/é"):
            seed = json.loads(json.dumps(self.seed))
            seed["install_files"][0]["guest_path"] = bad
            result = self.check(seed=seed)
            self.assertIn("guest_path", self.codes(result), bad)

    def test_guest_path_space_allowed_but_byte_limit_enforced(self):
        self.assertEqual(seed_preflight._guest_path("/usr/share/a b"), "/usr/share/a b")
        with self.assertRaises(ValueError):
            seed_preflight._guest_path("/" + "a" * 255)

    def test_casefold_collision_and_file_directory_conflict(self):
        seed = json.loads(json.dumps(self.seed))
        seed["install_files"].append({**seed["install_files"][0], "guest_path": "/USR/bin/other"})
        seed["install_files"].append({**seed["install_files"][0], "guest_path": "/usr/bin/x86_64-elf-gcc/child"})
        codes = self.codes(self.check(seed=seed))
        self.assertIn("fat_case_collision", codes)
        self.assertIn("file_directory_conflict", codes)

    def test_duplicate_across_seed_and_sysroot_rejected(self):
        seed = json.loads(json.dumps(self.seed))
        seed["install_files"].append({**seed["install_files"][0],
                                       "guest_path": "/sysroot/include/api.h"})
        sysroot = {"files": [{**self.sys_files[0], "guest_path": "/sysroot/include/api.h"}]}
        result = self.check(seed=seed, sysroot=sysroot)
        self.assertIn("duplicate_guest_path", self.codes(result))

    def test_sysroot_paths_are_explicit_and_never_rewritten(self):
        sysroot = {"files": [{**self.sys_files[0], "guest_path": "/include/api.h"}]}
        self.assertIn("sysroot_mapping", self.codes(self.check(sysroot=sysroot)))

    def test_hash_and_declared_size_checked(self):
        seed = json.loads(json.dumps(self.seed))
        seed["install_files"][0]["sha256"] = "0" * 64
        seed["install_files"][1]["bytes"] += 1
        codes = self.codes(self.check(seed=seed))
        self.assertIn("sha256_mismatch", codes)
        self.assertIn("size_mismatch", codes)

    def test_tool_whitelist_and_install_mapping_are_enforced(self):
        seed = json.loads(json.dumps(self.seed))
        seed["tools"]["rm"] = dict(seed["tools"]["gcc"])
        seed["tools"]["gcc"]["guest_path"] = "/tmp/host-tool"
        codes = self.codes(self.check(seed=seed))
        self.assertIn("tool_not_whitelisted", codes)
        self.assertIn("tool_mapping_mismatch", codes)

    def test_tool_path_hash_and_explicit_guest_path_select_alias(self):
        seed = json.loads(json.dumps(self.seed))
        gcc_install = next(row for row in seed["install_files"]
                           if row["guest_path"] == seed["tools"]["gcc"]["guest_path"])
        seed["install_files"].append({**gcc_install,
                                      "guest_path": "/usr/bin/x86_64-elf-gcc-16.2.0"})
        self.assertTrue(self.check(seed=seed).ok, self.check(seed=seed).diagnostics)
        del seed["tools"]["gcc"]["guest_path"]
        result = self.check(seed=seed)
        self.assertIn("tool_mapping_ambiguous", self.codes(result))

    def test_tool_must_be_static_amd64_exec(self):
        for bad, expected in ((b"not ELF", "elf_header"),
                              (make_elf(interpreter=True), "elf_phdr_unsupported"),
                              (make_elf(dynamic=True), "elf_phdr_unsupported"),
                              (make_elf(load_flags=7), "elf_permissions"),
                              (make_elf(entry=0x50000000), "elf_entry")):
            tool_path = self.seed_root / "tools/gcc"
            tool_path.write_bytes(bad)
            seed = json.loads(json.dumps(self.seed))
            digest = hashlib.sha256(bad).hexdigest()
            for row in [seed["install_files"][0], seed["tools"]["gcc"]]:
                row["sha256"] = digest
                row["bytes"] = len(bad)
            self.assertIn(expected, self.codes(self.check(seed=seed)), expected)
            tool_path.write_bytes(make_elf())

    def test_tls_static_subset_valid_and_rejects_bounds(self):
        good = make_elf(tls=(0x1000, 0x40000000, 4, 32, 16))
        (self.seed_root / "tools/gcc").write_bytes(good)
        seed = json.loads(json.dumps(self.seed))
        for row in [seed["install_files"][0], seed["tools"]["gcc"]]:
            row["sha256"] = hashlib.sha256(good).hexdigest()
            row["bytes"] = len(good)
        self.assertTrue(self.check(seed=seed).ok)
        bad = make_elf(tls=(0x1000, 0x40000000, 4, (1 << 20) + 1, 16))
        (self.seed_root / "tools/gcc").write_bytes(bad)
        for row in [seed["install_files"][0], seed["tools"]["gcc"]]:
            row["sha256"] = hashlib.sha256(bad).hexdigest()
            row["bytes"] = len(bad)
        self.assertIn("elf_tls_alignment", self.codes(self.check(seed=seed)))

    def test_loads_may_not_overlap_tls_heap_or_reserved_budget(self):
        data = make_elf(load_address=0x5FE00000)
        (self.seed_root / "tools/gcc").write_bytes(data)
        seed = json.loads(json.dumps(self.seed))
        for row in [seed["install_files"][0], seed["tools"]["gcc"]]:
            row["sha256"] = hashlib.sha256(data).hexdigest()
            row["bytes"] = len(data)
        self.assertIn("elf_reserved_overlap", self.codes(self.check(seed=seed)))

    def test_actual_image_end_excludes_guard_stack_and_startup(self):
        # The final legal LOAD page may end at 0x7ffdb000; the next page is the guard.
        elf = bytearray(make_elf(load_address=0x7FFDA000))
        phoff = 64
        struct.pack_into("<Q", elf, phoff + 40, 0x1000)
        data = bytes(elf)
        (self.seed_root / "tools/gcc").write_bytes(data)
        seed = json.loads(json.dumps(self.seed))
        for row in [seed["install_files"][0], seed["tools"]["gcc"]]:
            row["sha256"] = hashlib.sha256(data).hexdigest()
            row["bytes"] = len(data)
        self.assertTrue(self.check(seed=seed).ok)
        struct.pack_into("<Q", elf, phoff + 16, 0x7FFDB000)
        struct.pack_into("<Q", elf, 24, 0x7FFDB000)
        data = bytes(elf)
        (self.seed_root / "tools/gcc").write_bytes(data)
        for row in [seed["install_files"][0], seed["tools"]["gcc"]]:
            row["sha256"] = hashlib.sha256(data).hexdigest()
            row["bytes"] = len(data)
        self.assertIn("elf_load_bounds", self.codes(self.check(seed=seed)))

    def test_host_cxx_is_not_implicitly_a_target_sysroot(self):
        seed = json.loads(json.dumps(self.seed))
        seed["host_stdcxx"] = {"path": "host-runtime"}
        (self.seed_root / "host-runtime").mkdir()
        sysroot = {"files": [{**self.sys_files[0], "path": "host-runtime/include/c++/vector"}]}
        (self.seed_root / "host-runtime/include/c++").mkdir(parents=True)
        (self.seed_root / "host-runtime/include/c++/vector").write_text("host header")
        self.assertIn("host_runtime_in_sysroot", self.codes(self.check(seed=seed, sysroot=sysroot)))

    def test_sdk_manifest_hash_and_explicit_input_hashes_checked(self):
        sdk_file = self.seed_root / "sdk/api.h"
        sdk_file.write_text("int sdk;\n")
        sdk_hash = hashlib.sha256(sdk_file.read_bytes()).hexdigest()
        sdk_doc = {"files": [{"path": "api.h", "sha256": sdk_hash}]}
        sdk_bytes = json.dumps(sdk_doc).encode()
        (self.seed_root / "sdk/manifest.json").write_bytes(sdk_bytes)
        seed = json.loads(json.dumps(self.seed))
        seed["sdk_manifest"]["sha256"] = "0" * 64
        seed["sdk_input_hashes"] = {"api.h": "f" * 64}
        codes = self.codes(self.check(seed=seed))
        self.assertIn("sha256_mismatch", codes)
        self.assertIn("sdk_input_manifest_mismatch", codes)
        self.assertIn("sha256_mismatch", codes)


if __name__ == "__main__":
    unittest.main()
