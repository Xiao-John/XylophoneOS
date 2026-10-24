#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read-only validation of an XOS GCC Seed and explicit target sysroot bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


USER_BEGIN = 0x40000000
IMAGE_END = 0x7FFDB000
STACK_GUARD = 0x7FFDB000
HEAP_BEGIN = 0x60000000
HEAP_END = 0x70000000
TLS_BEGIN = 0x5FE00000
TLS_END = HEAP_BEGIN
RESERVED_PAGES = 36
MAX_PAGES = 65536
TLS_MAX_BYTES = 1 << 20
TLS_MAX_ALIGNMENT = 1 << 16
PAGE_SIZE = 4096
TOOL_WHITELIST = frozenset({
    "gcc", "g++", "cc1", "cc1plus", "cpp", "collect2", "as", "ld", "ar",
    "ranlib", "strip", "nm", "objcopy", "objdump", "readelf", "size",
})


@dataclass
class PreflightResult:
    """Serializable validation report. A valid report is still not guest execution."""

    ok: bool = True
    seed_files: list[dict[str, Any]] = field(default_factory=list)
    sysroot_files: list[dict[str, Any]] = field(default_factory=list)
    tools: dict[str, dict[str, Any]] = field(default_factory=dict)
    diagnostics: list[dict[str, str]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def add(self, code: str, message: str, *, source: str = "bundle",
            path: str = "") -> None:
        self.ok = False
        self.diagnostics.append({"severity": "error", "code": code,
                                 "source": source, "path": path,
                                 "message": message})

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "not_guest_test": True,
                "seed_files": self.seed_files, "sysroot_files": self.sysroot_files,
                "tools": self.tools, "summary": self.summary,
                "diagnostics": self.diagnostics}


def _load_manifest(value: str | os.PathLike[str] | Mapping[str, Any],
                   result: PreflightResult, label: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        data = json.loads(Path(value).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("manifest root must be an object")
        return data
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        result.add("manifest_read", f"cannot read {label} manifest: {exc}", source=label,
                   path=str(value))
        return {}


def _safe_relative(raw: Any) -> PurePosixPath:
    if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
        raise ValueError("source path must be a nonempty POSIX relative path")
    if raw.startswith("/") or (len(raw) >= 2 and raw[1] == ":"):
        raise ValueError("host absolute source paths are forbidden")
    parts = raw.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("source path contains empty, dot, or parent component")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        raise ValueError("source path contains a control character")
    if len(raw.encode("utf-8")) > 4096:
        raise ValueError("source path is unreasonably long")
    return PurePosixPath(*parts)


def _guest_path(raw: Any) -> str:
    if not isinstance(raw, str) or not raw.startswith("/") or raw == "/":
        raise ValueError("guest path must be an absolute file path")
    if "\\" in raw or "\x00" in raw or raw.endswith("/") or "//" in raw:
        raise ValueError("guest path is not canonical")
    if len(raw.encode("utf-8")) > 255:
        raise ValueError("guest path exceeds 255 UTF-8 bytes")
    if any(ord(ch) < 32 or ord(ch) == 127 or ord(ch) > 127 for ch in raw):
        raise ValueError("guest path must be ASCII and contain no controls")
    parts = raw[1:].split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("guest path contains empty, dot, or parent component")
    invalid_fat = set('"*:<>?\\|')
    if any(any(ch in invalid_fat for ch in part) for part in parts):
        raise ValueError("guest path contains a FAT-incompatible character")
    return raw


def _read_source(root: Path, raw: Any, result: PreflightResult, source: str) -> tuple[bytes | None, str]:
    try:
        rel = _safe_relative(raw)
    except ValueError as exc:
        result.add("source_path", str(exc), source=source, path=str(raw))
        return None, str(raw)
    if rel.parts and rel.parts[0].casefold() == "localpilot":
        result.add("source_isolated_project", "source paths may not enter the isolated localpilot project",
                   source=source, path=rel.as_posix())
        return None, rel.as_posix()
    root_abs = root.absolute()
    current = root_abs
    try:
        if stat.S_ISLNK(current.lstat().st_mode):
            raise ValueError("explicit source root is a symlink")
        if not current.is_dir():
            raise ValueError("explicit source root is not a directory")
        for part in rel.parts:
            current = current / part
            mode = current.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise ValueError("source path traverses a symlink")
        if not current.is_file():
            raise ValueError("source is not a regular file")
        return current.read_bytes(), rel.as_posix()
    except (OSError, ValueError) as exc:
        result.add("source_file", str(exc), source=source, path=rel.as_posix())
        return None, rel.as_posix()


def _hash_file(data: bytes, expected: Any, result: PreflightResult,
               source: str, path: str) -> str | None:
    actual = hashlib.sha256(data).hexdigest()
    if not isinstance(expected, str) or len(expected) != 64:
        result.add("sha256_format", "manifest sha256 must be 64 hex characters",
                   source=source, path=path)
        return actual
    if actual != expected.lower():
        result.add("sha256_mismatch", f"sha256 mismatch: expected {expected}, got {actual}",
                   source=source, path=path)
    return actual


def _path_registry(paths: list[tuple[str, str, str]], result: PreflightResult) -> None:
    """Check duplicates, FAT case-fold collisions, and file/directory conflicts."""
    spelling: dict[str, tuple[str, str]] = {}
    files: set[str] = set()
    for guest, source, original in paths:
        components = guest.lstrip("/").split("/")
        for i in range(1, len(components) + 1):
            prefix = "/" + "/".join(components[:i])
            folded = prefix.casefold()
            previous = spelling.get(folded)
            if previous and previous[0] != prefix:
                result.add("fat_case_collision",
                           f"case-insensitive FAT collision with {previous[0]} ({previous[1]})",
                           source=source, path=prefix)
            else:
                spelling[folded] = (prefix, source)
        folded_guest = guest.casefold()
        if folded_guest in files:
            result.add("duplicate_guest_path", "guest destination is duplicated",
                       source=source, path=guest)
        for existing in files:
            if folded_guest.startswith(existing + "/") or existing.startswith(folded_guest + "/"):
                result.add("file_directory_conflict",
                           "guest file path conflicts with another file's directory prefix",
                           source=source, path=guest)
        files.add(folded_guest)


def _align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def _elf_check(data: bytes, result: PreflightResult, source: str, path: str) -> dict[str, Any] | None:
    def fail(code: str, message: str) -> None:
        result.add(code, message, source=source, path=path)

    if len(data) < 64 or data[:4] != b"\x7fELF":
        fail("elf_header", "tool is not a complete ELF file")
        return None
    if data[4] != 2 or data[5] != 1 or data[6] != 1:
        fail("elf_class", "tool must be ELF64 little-endian version 1")
        return None
    try:
        ident_osabi = data[7]
        etype, machine, version = struct.unpack_from("<HHI", data, 16)
        entry, phoff = struct.unpack_from("<QQ", data, 24)
        ehsize, phentsize, phnum = struct.unpack_from("<HHH", data, 52)
        flags = struct.unpack_from("<I", data, 48)[0]
    except struct.error:
        fail("elf_header", "truncated ELF header")
        return None
    if etype != 2 or machine != 62 or version != 1 or ident_osabi not in (0, 3) or flags != 0:
        fail("elf_target", "tool must be XOS static AMD64 ET_EXEC (OSABI 0/3, flags 0)")
    if ehsize != 64 or phentsize != 56 or not 0 < phnum <= 32 or phoff < 64 or phoff + phnum * 56 > len(data):
        fail("elf_phdr", "invalid or out-of-range program header table")
        return None
    loads: list[tuple[int, int, int, int, int]] = []
    tls = None
    entry_found = False
    for i in range(phnum):
        kind, pflags, offset, address, _paddr, filesz, memsz, alignment = struct.unpack_from("<IIQQQQQQ", data, phoff + i * 56)
        if kind == 7:
            if filesz == 0 and memsz == 0:
                continue
            if tls is not None or pflags not in (4, 6):
                fail("elf_tls", "only one read-only or read/write static PT_TLS is supported")
            if filesz > memsz or offset + filesz > len(data) or address < USER_BEGIN or address >= IMAGE_END or memsz > IMAGE_END - address:
                fail("elf_tls_bounds", "PT_TLS is out of range")
            alignment = alignment or 1
            if memsz > TLS_MAX_BYTES or alignment > TLS_MAX_ALIGNMENT or alignment & (alignment - 1) or address % alignment or offset % alignment:
                fail("elf_tls_alignment", "PT_TLS exceeds static size/alignment policy")
            tls = (offset, address, filesz, memsz, alignment)
            continue
        if kind != 1:
            allowed = kind in (0, 4, 6, 0x6474E552) or (kind == 0x6474E551 and not (pflags & 1))
            if not allowed:
                fail("elf_phdr_unsupported", f"unsupported program header type {kind}")
            continue
        if filesz == 0 and memsz == 0:
            continue
        if filesz > memsz or offset + filesz > len(data) or address < USER_BEGIN or address >= IMAGE_END or memsz > IMAGE_END - address:
            fail("elf_load_bounds", "PT_LOAD file or virtual range is invalid")
            continue
        if alignment > 1 and (alignment & (alignment - 1) or address % alignment != offset % alignment):
            fail("elf_load_alignment", "PT_LOAD alignment is invalid")
        if address % PAGE_SIZE != offset % PAGE_SIZE:
            fail("elf_page_alignment", "PT_LOAD page offsets are incongruent")
        if pflags & ~7 or not (pflags & 4) or (pflags & 3) == 3:
            fail("elf_permissions", "PT_LOAD must be readable and must not be W+X")
        first = address & ~(PAGE_SIZE - 1)
        end = _align_up(address + memsz, PAGE_SIZE)
        if first < HEAP_END and TLS_BEGIN < end:
            fail("elf_reserved_overlap", "PT_LOAD overlaps the reserved TLS/heap interval")
        for old in loads:
            if first < old[1] and old[0] < end:
                fail("elf_load_overlap", "PT_LOAD page ranges overlap")
        if len(loads) >= 8:
            fail("elf_load_count", "more than eight nonempty PT_LOAD segments")
        loads.append((first, end, address, filesz, pflags))
        if pflags & 1 and address <= entry < address + filesz:
            entry_found = True
    if not loads:
        fail("elf_no_load", "tool has no nonempty PT_LOAD segment")
    if not entry_found:
        fail("elf_entry", "entry is not in file-backed executable PT_LOAD bytes")
    if tls and tls[2]:
        off, addr, fsz, _msz, _align = tls
        contained = False
        for i in range(phnum):
            fields = struct.unpack_from("<IIQQQQQQ", data, phoff + i * 56)
            if fields[0] == 1:
                _k, _f, lo, va, _pa, fs, _ms, _al = fields
                if off >= lo and fsz <= fs and off - lo <= fs - fsz and addr >= va and addr - va == off - lo:
                    contained = True
        if not contained:
            fail("elf_tls_load", "initialized PT_TLS bytes are not contained in matching PT_LOAD bytes")
    pages = sum((end - first) // PAGE_SIZE for first, end, *_ in loads)
    tls_pages = 0
    if tls:
        _off, _addr, _filesz, memsz, align = tls
        size = _align_up(memsz, align)
        tp = _align_up(TLS_BEGIN + size, max(align, 16))
        tls_end = _align_up(tp + 16, PAGE_SIZE)
        tls_pages = (tls_end - TLS_BEGIN) // PAGE_SIZE
        if tls_end > TLS_END:
            fail("elf_tls_reserve", "static TLS allocation exceeds reserved TLS arena")
    if pages + tls_pages + RESERVED_PAGES > MAX_PAGES:
        fail("elf_page_budget", "tool image plus TLS and reserved stack/startup pages exceeds task page budget")
    return {"entry": entry, "load_pages": pages, "tls_pages": tls_pages,
            "phnum": phnum, "elf_type": "ET_EXEC", "machine": "AMD64"}


def _items(value: Any, key: str, result: PreflightResult, source: str) -> list[dict[str, Any]]:
    items = value.get(key, []) if isinstance(value, dict) else []
    if not isinstance(items, list):
        result.add("manifest_schema", f"{key} must be a list", source=source)
        return []
    return [item if isinstance(item, dict) else {} for item in items]


def validate_bundle(seed_manifest: str | os.PathLike[str] | Mapping[str, Any],
                    seed_root: str | os.PathLike[str],
                    sysroot_manifest: str | os.PathLike[str] | Mapping[str, Any],
                    sysroot_root: str | os.PathLike[str],
                    guest_sysroot_root: str = "/sysroot",
                    required_tools: tuple[str, ...] = ("gcc", "as", "ld", "ar", "ranlib")) -> PreflightResult:
    """Validate explicit Seed and target sysroot manifests without copying/executing.

    Source paths are interpreted only relative to the corresponding explicit roots.
    The returned entries are prospective mappings, not installed files.
    """
    report = PreflightResult()
    seed = _load_manifest(seed_manifest, report, "seed")
    sysroot = _load_manifest(sysroot_manifest, report, "sysroot")
    try:
        if (not isinstance(guest_sysroot_root, str) or not guest_sysroot_root.startswith("/") or
                guest_sysroot_root == "/" or guest_sysroot_root.endswith("/") or "//" in guest_sysroot_root or
                any(part in ("", ".", "..") for part in guest_sysroot_root[1:].split("/"))):
            raise ValueError("guest sysroot root must be canonical absolute directory")
        if any(ord(ch) < 32 or ord(ch) == 127 or ord(ch) > 127 for ch in guest_sysroot_root):
            raise ValueError("guest sysroot root must be ASCII and contain no controls")
    except ValueError as exc:
        report.add("guest_sysroot_root", str(exc), source="sysroot", path=guest_sysroot_root)
    seed_root_path, sysroot_root_path = Path(seed_root), Path(sysroot_root)
    seed_rows = _items(seed, "install_files", report, "seed")
    sysroot_rows = _items(sysroot, "files", report, "sysroot")
    all_paths: list[tuple[str, str, str]] = []
    seed_by_source: dict[str, list[dict[str, Any]]] = {}
    total_bytes = 0

    def validate_rows(rows: list[dict[str, Any]], root: Path, label: str,
                      destination_prefix: str | None) -> list[dict[str, Any]]:
        nonlocal total_bytes
        validated: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            source_path = str(row.get("path", ""))
            try:
                guest = _guest_path(row.get("guest_path"))
                if destination_prefix is not None and not (guest == destination_prefix or guest.startswith(destination_prefix + "/")):
                    report.add("sysroot_mapping", "sysroot guest_path must explicitly include guest_sysroot_root; paths are never rewritten",
                               source=label, path=guest)
            except ValueError as exc:
                report.add("guest_path", str(exc), source=label, path=str(row.get("guest_path", "")))
                guest = ""
            data, normalized = _read_source(root, row.get("path"), report, label)
            actual = None
            if data is not None:
                actual = _hash_file(data, row.get("sha256"), report, label, normalized)
                total_bytes += len(data)
                declared = row.get("bytes")
                if declared is not None and declared != len(data):
                    report.add("size_mismatch", f"declared bytes {declared} != actual {len(data)}",
                               source=label, path=normalized)
            entry = {"source_path": normalized, "guest_path": guest,
                     "sha256": actual, "expected_sha256": row.get("sha256"),
                     "bytes": len(data) if data is not None else None,
                     "role": "target_sysroot" if label == "sysroot" else "seed_install"}
            validated.append(entry)
            if guest:
                all_paths.append((guest, label, normalized))
            if label == "seed":
                seed_by_source.setdefault(normalized, []).append(entry)
        return validated

    report.seed_files = validate_rows(seed_rows, seed_root_path, "seed", None)
    report.sysroot_files = validate_rows(sysroot_rows, sysroot_root_path, "sysroot", guest_sysroot_root)
    _path_registry(all_paths, report)

    if not isinstance(seed.get("tools", {}), dict):
        report.add("tools_schema", "tools must be an object", source="seed")
        tool_rows: dict[str, Any] = {}
    else:
        tool_rows = seed.get("tools", {})
    for name, raw in tool_rows.items():
        if name not in TOOL_WHITELIST:
            report.add("tool_not_whitelisted", f"tool {name!r} is not in the supported tool whitelist",
                       source="seed", path=str(name))
        if not isinstance(raw, dict):
            report.add("tool_schema", "tool record must be an object", source="seed", path=str(name))
            continue
        source_raw = raw.get("path")
        try:
            source_key = _safe_relative(source_raw).as_posix()
        except ValueError as exc:
            report.add("tool_host_path", str(exc), source="seed", path=str(source_raw))
            source_key = ""
        guest_raw = raw.get("guest_path")
        if guest_raw is None:
            candidates = [item for item in seed_by_source.get(source_key, [])
                          if item["expected_sha256"] == raw.get("sha256")]
            if len(candidates) > 1:
                report.add("tool_mapping_ambiguous",
                           "tool source has multiple installation guest paths; manifest must select guest_path",
                           source="seed", path=source_key)
                guest = ""
            elif len(candidates) == 1:
                guest = candidates[0]["guest_path"]
            else:
                report.add("tool_not_installed", "tool path/hash is absent from install_files",
                           source="seed", path=source_key)
                guest = ""
        else:
            try:
                guest = _guest_path(guest_raw)
            except ValueError as exc:
                report.add("tool_guest_path", str(exc), source="seed", path=str(guest_raw))
                guest = ""
        candidates = seed_by_source.get(source_key, [])
        matching = [item for item in candidates
                    if item["guest_path"] == guest and item["expected_sha256"] == raw.get("sha256")]
        if not candidates:
            report.add("tool_not_installed", "tool path is absent from install_files",
                       source="seed", path=source_key)
        elif guest and not matching:
            report.add("tool_mapping_mismatch",
                       "tool path, guest_path, and sha256 must match one install_files entry",
                       source="seed", path=guest)
        data, normalized = _read_source(seed_root_path, source_raw, report, "tool")
        elf_info = None
        actual_hash = None
        if data is not None:
            actual_hash = _hash_file(data, raw.get("sha256"), report, "tool", normalized)
            elf_info = _elf_check(data, report, "tool", normalized)
        report.tools[str(name)] = {"source_path": normalized, "guest_path": guest,
                                   "sha256": actual_hash, "elf": elf_info}
    for name in required_tools:
        if name not in tool_rows:
            report.add("required_tool_missing", f"required tool {name!r} is absent",
                       source="seed", path=name)

    sdk = seed.get("sdk_manifest")
    sdk_path = sdk.get("path") if isinstance(sdk, dict) else sdk if isinstance(sdk, str) else None
    sdk_hash = (sdk.get("sha256") if isinstance(sdk, dict) else None) or seed.get("sdk_manifest_sha256")
    if sdk_path is not None:
        sdk_data, sdk_normalized = _read_source(seed_root_path, sdk_path, report, "sdk_manifest")
        if sdk_data is not None:
            _hash_file(sdk_data, sdk_hash, report, "sdk_manifest", sdk_normalized)
            try:
                sdk_doc = json.loads(sdk_data.decode("utf-8"))
                sdk_dir = PurePosixPath(sdk_normalized).parent
                input_hashes = seed.get("sdk_input_hashes", {})
                if isinstance(input_hashes, dict):
                    inputs = input_hashes.items()
                elif isinstance(input_hashes, list):
                    inputs = ((item.get("path"), item.get("sha256")) for item in input_hashes if isinstance(item, dict))
                elif input_hashes is None:
                    inputs = ()
                else:
                    report.add("sdk_inputs_schema", "sdk_input_hashes must be object or list", source="sdk_manifest")
                    inputs = ()
                sdk_actual_by_path = {}
                for row in _items(sdk_doc, "files", report, "sdk_manifest"):
                    path = row.get("path")
                    if isinstance(path, str):
                        sdk_actual_by_path[path] = row.get("sha256")
                for input_path, expected in inputs:
                    try:
                        input_rel = _safe_relative(input_path)
                        actual_in_manifest = sdk_actual_by_path.get(input_rel.as_posix())
                        if actual_in_manifest is not None and actual_in_manifest != expected:
                            report.add("sdk_input_manifest_mismatch", "sdk_input_hashes differs from SDK manifest",
                                       source="sdk_manifest", path=input_rel.as_posix())
                        sdk_root = seed_root_path.joinpath(*sdk_dir.parts)
                        input_data, input_norm = _read_source(sdk_root, input_rel.as_posix(), report, "sdk_input")
                        if input_data is not None:
                            _hash_file(input_data, expected, report, "sdk_input", input_norm)
                    except ValueError as exc:
                        report.add("sdk_input_path", str(exc), source="sdk_manifest", path=str(input_path))
            except (UnicodeError, json.JSONDecodeError) as exc:
                report.add("sdk_manifest_json", f"invalid SDK manifest JSON: {exc}",
                           source="sdk_manifest", path=sdk_normalized)
    elif sdk_hash is not None:
        report.add("sdk_manifest_path_missing", "sdk manifest hash is present without an explicit path",
                   source="sdk_manifest")

    host_stdcxx = seed.get("host_stdcxx")
    if isinstance(host_stdcxx, dict) and isinstance(host_stdcxx.get("path"), str):
        try:
            host_prefix = _safe_relative(host_stdcxx["path"]).as_posix().rstrip("/") + "/"
            for row in sysroot_rows:
                sys_path = _safe_relative(row.get("path")).as_posix()
                if sys_path == host_prefix[:-1] or sys_path.startswith(host_prefix):
                    report.add("host_runtime_in_sysroot",
                               "host C++ runtime source is mixed into target sysroot; target files must be explicit",
                               source="sysroot", path=sys_path)
        except ValueError as exc:
            report.add("host_runtime_path", str(exc), source="seed", path=str(host_stdcxx["path"]))

    report.summary = {"seed_files": len(report.seed_files),
                      "sysroot_files": len(report.sysroot_files),
                      "tools_checked": len(report.tools), "mapped_bytes": total_bytes,
                      "errors": len(report.diagnostics), "guest_sysroot_root": guest_sysroot_root,
                      "not_guest_test": True}
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-manifest", required=True)
    parser.add_argument("--seed-root", required=True)
    parser.add_argument("--sysroot-manifest", required=True)
    parser.add_argument("--sysroot-root", required=True)
    parser.add_argument("--guest-sysroot-root", default="/sysroot")
    parser.add_argument("--required-tool", action="append", dest="required_tools")
    parser.add_argument("--report", help="write JSON report to this explicit path; stdout otherwise")
    args = parser.parse_args(argv)
    report = validate_bundle(args.seed_manifest, args.seed_root, args.sysroot_manifest,
                             args.sysroot_root, args.guest_sysroot_root,
                             tuple(args.required_tools) if args.required_tools else ("gcc", "as", "ld", "ar", "ranlib"))
    rendered = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    if args.report:
        Path(args.report).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
