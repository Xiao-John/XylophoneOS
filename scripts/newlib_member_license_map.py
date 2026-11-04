#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Map every newlib archive member to its source file and declaration category.

For each member of ``build/sdk/lib/libc.a`` and ``libm.a`` this script resolves the
originating source file, reads the copyright/license declaration in that file's
header and assigns a declaration category.  The category is a *declaration
extraction*, not a legal opinion; the authoritative multi-source terms live in
``src/third_party/newlib/COPYING.NEWLIB``.

Member names come from GNU ar (long names live in the ``//`` table and are
referenced as ``/<offset>``).  Source paths come from the ``.deps/*.Po``
dependency files of a newlib build tree, which record the file actually
compiled; when no dependency file is available the script falls back to a
stem search with target-architecture preferences.
"""
import argparse
import collections
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SDK_ARCHIVES = ("build/sdk/lib/libc.a", "build/sdk/lib/libm.a")
# Build trees that recorded dependency files, best first.  All of them agree on
# the ambiguous cases (verified: math/mathfp, stdlib/libgloss, machine dirs).
DEPENDENCY_TREES = (
    "build/w1_final_acceptance/newlib/single/build/x86_64-elf",
    "build/w1_final_acceptance/newlib/threaded/build/x86_64-elf",
    ".cache/xos_seed/threading_newlib/build/x86_64-elf",
)
SOURCE_TREE_PREFIX = "build/w1_final_acceptance/newlib/newlib-4.6.0.20260123"
SOURCE_SUFFIXES = (".c", ".S", ".s", ".cc", ".cpp")
TARGET_MACHINES = ("x86_64", "i386")

DECLARATION_WINDOW = None  # whole file: a few sources carry the copyright below line 160


def iter_archive_members(path):
    """Yield member names of a GNU ``!<arch>`` archive in order."""
    data = path.read_bytes()
    if data[:8] != b"!<arch>\n":
        raise SystemExit(f"not a plain ar archive: {path}")
    offset, longnames = 8, None
    while offset + 60 <= len(data):
        header = data[offset:offset + 60]
        name = header[0:16].decode("ascii", "replace")
        size = int(header[48:58].decode().strip())
        body = offset + 60
        if name.startswith("//"):
            longnames = data[body:body + size]
        token = name.strip()
        if token in ("/", "//") or token.startswith("/SYM"):
            pass
        elif token.startswith("/") and token[1:].isdigit() and longnames is not None:
            start = int(token[1:])
            end = longnames.find(b"/\n", start)
            yield longnames[start:end if end >= 0 else None].decode()
        else:
            yield token.rstrip("/")
        offset = body + size
        if offset % 2:
            offset += 1


def load_dependency_map():
    """Map object basename -> tree-relative source path, first tree wins."""
    mapping = {}
    for tree in DEPENDENCY_TREES:
        root = ROOT / tree
        if not root.is_dir():
            continue
        for dep in root.rglob(".deps/*.Po"):
            source = dependency_source(dep)
            member = dep.name[:-3] + ".o"  # libc_a-isalnum.Po -> libc_a-isalnum.o
            if source is not None and member not in mapping:
                mapping[member] = source
    return mapping


def dependency_source(dep_path):
    """First compiled source file listed by a ``.Po`` dependency file."""
    text = dep_path.read_text(errors="replace")
    for token in re.split(r"[\s\\]+", text):
        if token.endswith(SOURCE_SUFFIXES) and "newlib-4.6.0.20260123/" in token:
            return token.split("newlib-4.6.0.20260123/", 1)[1]
    return None


def stem_index():
    """Source-tree index of candidate files by stem (fallback resolver)."""
    tree = ROOT / SOURCE_TREE_PREFIX
    index = collections.defaultdict(list)
    if tree.is_dir():
        for path in tree.rglob("*"):
            if path.is_file() and path.suffix in SOURCE_SUFFIXES:
                index[path.stem].append(path.relative_to(tree).as_posix())
    return index


def fallback_group(relative):
    """Preference group for a fallback candidate: A generic, B target, C other, D test."""
    parts = relative.split("/")
    if "testsuite" in parts:
        return "D"
    if "machine" in parts:
        position = parts.index("machine")
        architecture = parts[position + 1] if position + 1 < len(parts) else ""
        return "B" if architecture in TARGET_MACHINES else "C"
    if parts[:1] == ["libgloss"] or "sys" in parts:
        return "C"
    return "A"


def resolve_fallback(member, index):
    """Resolve a member without a dependency record; return (path, note)."""
    base = member.split("-", 1)[1]
    base = base[:-2] if base.endswith(".o") else base
    candidates = index.get(base, [])
    if not candidates:
        return None, "no_source_candidate"
    if len(candidates) == 1:
        return candidates[0], "unique_stem"
    groups = collections.defaultdict(list)
    for candidate in candidates:
        groups[fallback_group(candidate)].append(candidate)
    if len(groups["A"]) == 1:
        return groups["A"][0], "generic_directory_preference"
    if not groups["A"] and len(groups["B"]) == 1:
        return groups["B"][0], "target_machine_preference"
    union = groups["A"] + groups["B"]
    if len(union) == 1:
        return union[0], "generic_or_target_unique"
    return None, "ambiguous_stem:" + "|".join(sorted(candidates[:6]))


DECLARATION_RULES = (
    ("spdx", re.compile(r"SPDX-License-Identifier:\s*(\S+)")),
    ("lgpl", re.compile(r"(GNU (Lesser|Library) General Public License|LGPL)", re.I)),
    ("gpl", re.compile(r"GNU General Public License|\bGPL\b", re.I)),
    ("bsd_like", re.compile(r"Redistribution and use in source and binary forms", re.I)),
    ("mit_like", re.compile(r"Permission to use, copy, modify, and/or distribute", re.I)),
    ("other_copyright", re.compile(r"Copyright\s*(\(|©|\d)", re.I)),
)


def declaration_category(path):
    """Declaration category plus the matched text for one source file."""
    if path is None:
        return "no_declaration", None
    source = ROOT / SOURCE_TREE_PREFIX / path
    if not source.is_file():
        return "no_declaration", None
    body = source.read_text(errors="replace")
    if DECLARATION_WINDOW:
        body = "\n".join(body.splitlines()[:DECLARATION_WINDOW])
    for category, pattern in DECLARATION_RULES:
        match = pattern.search(body)
        if match:
            return category, match.group(0).strip()
    if re.search(r"copyright", body, re.I):
        return "other_copyright", None
    return "no_declaration", None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write the deterministic JSON report here")
    args = parser.parse_args()

    dependencies = load_dependency_map()
    index = stem_index()
    archives = {}
    unmapped, ambiguous, no_dependency = [], [], 0
    categories = collections.Counter()

    for archive in SDK_ARCHIVES:
        entries = []
        for member in sorted(set(iter_archive_members(ROOT / archive))):
            dependency = member if member.endswith(".o") else member + ".o"
            if dependency in dependencies:
                source, resolution = dependencies[dependency], "dependency_file"
            else:
                source, resolution = resolve_fallback(member, index)
                no_dependency += 1
            category, match = declaration_category(source)
            categories[category] += 1
            record = {"member": member, "source": source, "resolution": resolution,
                      "declaration_category": category}
            if match:
                record["declaration_text"] = match
            entries.append(record)
            if source is None:
                (ambiguous if resolution.startswith("ambiguous") else unmapped).append(
                    {"archive": archive, "member": member, "resolution": resolution})
        archives[archive] = {
            "members": entries,
            "member_count": len(entries),
            "resolved": sum(1 for entry in entries if entry["source"]),
        }

    report = {
        "version": 1,
        "generated_by": "scripts/newlib_member_license_map.py",
        "archives": archives,
        "totals": {
            "members": sum(entry["member_count"] for entry in archives.values()),
            "resolved": sum(entry["resolved"] for entry in archives.values()),
            "unmapped": len(unmapped),
            "ambiguous": len(ambiguous),
            "resolved_without_dependency_file": no_dependency,
        },
        "declaration_categories": dict(sorted(categories.items())),
        "dependency_trees": [tree for tree in DEPENDENCY_TREES if (ROOT / tree).is_dir()],
        "source_tree": SOURCE_TREE_PREFIX,
        "unmapped": unmapped,
        "ambiguous": ambiguous,
        "disclaimer": (
            "Declaration extraction, not a per-member legal opinion. Categories are "
            "matched from source headers; the authoritative multi-source terms are in "
            "src/third_party/newlib/COPYING.NEWLIB, whose sections apply per their own "
            "target restrictions (sections 21/22 are *-linux* targets only)."
        ),
    }
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    totals = report["totals"]
    print(f"members={totals['members']} resolved={totals['resolved']} "
          f"unmapped={totals['unmapped']} ambiguous={totals['ambiguous']} "
          f"categories={dict(sorted(categories.items()))}")
    if totals["unmapped"] or totals["ambiguous"]:
        print(f"sha256={hashlib.sha256(text.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
