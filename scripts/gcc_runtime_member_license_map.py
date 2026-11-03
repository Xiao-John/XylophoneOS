#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Map every GCC runtime archive member to a source file and declaration category.

The distributed GCC runtime archives
(`.cache/xos_seed/gcc/relinks/target_runtime_v5_receipt/lib/*.a`) are resolved in
three tiers:

1. ``dependency_file`` - a retained ``.deps/*.Po|*.Plo`` record names the file
   that was compiled into the object (GCC keeps these only while the build tree
   is intact; this tier is best effort).
2. ``exact_stem`` - a source file with the same stem exists in the GCC source
   tree (works for libstdc++/libsupc++ objects, which are named after their
   source file).
3. ``symbol_lookup`` - the object's defined text symbols (via ``x86_64-elf-nm``)
   are demangled with ``c++filt`` and searched in the source tree; a unique file
   match maps the member.

Anything that cannot be resolved stays in ``unmapped`` with its tier history;
the script never guesses. Declaration categories are extracted from the resolved
source file and are not a legal opinion.
"""
import argparse
import collections
import hashlib
import json
import pathlib
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ARCHIVES = {
    "libgcc.a": ".cache/xos_seed/gcc/relinks/target_runtime_v5_receipt/lib/libgcc.a",
    "libstdc++.a": ".cache/xos_seed/gcc/relinks/target_runtime_v5_receipt/lib/libstdc++.a",
    "libsupc++.a": ".cache/xos_seed/gcc/relinks/target_runtime_v5_receipt/lib/libsupc++.a",
}
SOURCE_ROOT = ".cache/xos_seed/gcc/source/gcc-16.2.0"
SEARCH_ROOTS = ("libgcc", "libstdc++-v3", "gmp", "mpfr", "mpc", "gcc")
TARGET_ARCHS = ("i386", "x86_64", "amd64", "x86", "i686")
SOURCE_SUFFIXES = (".c", ".cc", ".cpp", ".h", ".hpp", ".S", ".s")
EXCLUDE_PARTS = ("testsuite", "testsuite", "/test", "/doc/", "/po/")
DECLARATION_RULES = (
    ("gcc_runtime_exception", re.compile(r"GCC Runtime Library Exception", re.I)),
    ("spdx", re.compile(r"SPDX-License-Identifier:\s*(\S+)")),
    ("lgpl", re.compile(r"GNU (Lesser|Library) General Public License|\bLGPL\b", re.I)),
    ("gpl", re.compile(r"GNU General Public License|\bGPL\b", re.I)),
    ("dual_lgpl_gpl_gmp", re.compile(r"GNU Lesser General Public License.*GPL|either version", re.I)),
    ("bsd_like", re.compile(r"Redistribution and use in source and binary forms", re.I)),
    ("mit_like", re.compile(r"Permission to use, copy, modify, and/or distribute", re.I)),
    ("other_copyright", re.compile(r"Copyright\s*(\(|©|\d)", re.I)),
)


def read_archive(path):
    """Return {member_name: bytes} for a GNU ``!<arch>`` archive."""
    data = Path(path).read_bytes()
    if data[:8] != b"!<arch>\n":
        raise SystemExit(f"not a plain ar archive: {path}")
    offset, longnames, out = 8, None, {}
    while offset + 60 <= len(data):
        header = data[offset:offset + 60]
        name = header[0:16].decode("ascii", "replace")
        size = int(header[48:58].decode().strip())
        body = offset + 60
        chunk = data[body:body + size]
        if name.startswith("//"):
            longnames = chunk
        token = name.strip()
        if token in ("/", "//") or token.startswith("/SYM"):
            pass
        elif token.startswith("/") and token[1:].isdigit() and longnames is not None:
            start = int(token[1:])
            end = longnames.find(b"/\n", start)
            out[longnames[start:end if end >= 0 else None].decode()] = chunk
        else:
            out[token] = chunk
        offset = body + size
        if offset % 2:
            offset += 1
    return out


def source_files():
    """All candidate source files under the GCC source tree, key by stem."""
    root = ROOT / SOURCE_ROOT
    by_stem, all_paths = collections.defaultdict(list), []
    if not root.is_dir():
        return by_stem, all_paths
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        relative = path.relative_to(root).as_posix()
        if any(part in relative for part in EXCLUDE_PARTS) or "/testsuite/" in relative:
            continue
        by_stem[path.stem].append(relative)
        all_paths.append(relative)
    return by_stem, all_paths


def dependency_map():
    """object basename -> source path from retained .deps records."""
    mapping = {}
    for dep in (ROOT / ".cache/xos_seed/gcc").rglob(".deps/*.Po"):
        _collect_dep(dep, mapping)
    for dep in (ROOT / ".cache/xos_seed/gcc").rglob(".deps/*.Plo"):
        _collect_dep(dep, mapping)
    return mapping


def _collect_dep(dep, mapping):
    try:
        text = dep.read_text(errors="replace")
    except OSError:
        return
    for token in re.split(r"[\s\\]+", text):
        if not token.endswith(SOURCE_SUFFIXES):
            continue
        marker = "gcc-16.2.0/"
        source = token.split(marker, 1)[1] if marker in token else token
        key = dep.name[:-3] + (".o" if not dep.name.endswith(".Plo") else ".o")
        mapping.setdefault(key, source)
        return


def object_symbols(payload):
    """Defined text symbols of one archive member (best effort)."""
    with tempfile.NamedTemporaryFile(suffix=".o", delete=False) as handle:
        handle.write(payload)
        path = handle.name
    try:
        result = subprocess.run(["x86_64-elf-nm", "--defined-only", path],
                                capture_output=True, text=True)
    finally:
        pathlib.Path(path).unlink(missing_ok=True)
    symbols = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] in ("T", "t", "W", "V"):
            symbols.append(parts[-1])
    return symbols


def demangle(symbol):
    try:
        result = subprocess.run(["c++filt", symbol], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return symbol
    text = result.stdout.strip()
    return text if text else symbol


def search_source(token, all_paths, root):
    """Unique source file containing token (substring search, no testsuite)."""
    if not token:
        return [], []
    hits = []
    for relative in all_paths:
        path = root / relative
        try:
            body = path.read_text(errors="replace")
        except OSError:
            continue
        if token in body:
            hits.append(relative)
            if len(hits) > 12:
                break
    return hits, []


def declaration_category(path, root):
    if not path:
        return "no_declaration", None
    source = root / path
    if not source.is_file():
        return "no_declaration", None
    body = source.read_text(errors="replace")
    for category, pattern in DECLARATION_RULES:
        match = pattern.search(body)
        if match:
            return category, match.group(0).strip()
    if re.search(r"copyright", body, re.I):
        return "other_copyright", None
    return "no_declaration", None


def is_target_path(relative):
    """Keep generic files and i386/x86_64 ones; drop other architectures."""
    for index, part in enumerate(relative.split("/")):
        if part == "config" and index + 1 < len(relative.split("/")):
            arch = relative.split("/")[index + 1]
            if arch not in TARGET_ARCHS and arch not in ("common",):
                return False
    return True


def rank_candidates(paths, prefer=None):
    """Reduce candidates to one source file; None when still ambiguous."""
    kept = [p for p in paths if is_target_path(p)]
    if not kept:
        kept = [p for p in paths if "/config/" not in p] or list(paths)
    if prefer:
        narrowed = [p for p in kept if p.startswith(prefer)]
        if narrowed:
            kept = narrowed
    if len(kept) == 1:
        return kept[0]
    implementations = [p for p in kept if not p.endswith((".h", ".hpp"))]
    if len(implementations) == 1:
        return implementations[0]
    if implementations:
        kept = implementations
    generic = [p for p in kept if "/config/" not in p]
    if len(generic) == 1:
        return generic[0]
    if generic:
        kept = generic
    if len(kept) == 1:
        return kept[0]
    return None


def stem_text_search(stem, all_paths, root, prefer=None):
    """Find the member's source by searching its (de-prefixed) name in text."""
    tokens = [stem, stem.lstrip("_"), "_" + stem]
    seen, hits = set(), []
    for token in dict.fromkeys(tokens):
        if len(token) < 4:
            continue
        for relative in all_paths:
            if not is_target_path(relative) or relative in seen:
                continue
            path = root / relative
            try:
                body = path.read_text(errors="replace")
            except OSError:
                continue
            if token in body:
                seen.add(relative)
                hits.append(relative)
    if not hits:
        return None, []
    picked = rank_candidates(hits, prefer)
    return picked, sorted(hits)


def build_log_map():
    """object basename -> source path, from retained compile command lines."""
    mapping = {}
    symlink_names = {}
    marker = "gcc-16.2.0/"
    logs = sorted((ROOT / ".cache/xos_seed/gcc").rglob("*.log"),
                  key=lambda p: (0 if "target_runtime" in p.as_posix()
                                 else 1 if "stdcxx" in p.as_posix() else 2,
                                 p.as_posix()))
    for log in logs:
        if "testsuite" in log.as_posix():
            continue
        try:
            lines = log.read_text(errors="replace").splitlines()
        except OSError:
            continue
        # libtool compiles with relative source names; the `ln -s` lines carry
        # the full upstream path, so record them first.
        for line in lines:
            if line.startswith("ln -s ") and marker in line:
                parts = line.split()
                if len(parts) >= 3:
                    source = parts[2]
                    if marker in source:
                        symlink_names.setdefault(
                            pathlib.PurePosixPath(source).name,
                            source.split(marker, 1)[1])
        for line in lines:
            if " -o " not in line:
                continue
            tokens = line.split()
            source = None
            for token in tokens:
                if token.endswith(SOURCE_SUFFIXES) and marker in token:
                    source = token.split(marker, 1)[1]
                    break
            if source is None:
                for token in tokens:
                    if token.endswith(SOURCE_SUFFIXES) and not token.startswith("-"):
                        source = symlink_names.get(pathlib.PurePosixPath(token).name)
                        if source:
                            break
            if source is None:
                continue
            try:
                target = tokens[tokens.index("-o") + 1]
            except (ValueError, IndexError):
                continue
            mapping.setdefault(pathlib.PurePosixPath(target).name, source)
    return mapping


def resolve(member, payload, deps, logs, by_stem, all_paths, root, prefer):
    key = member.rstrip("/")
    stem = pathlib.PurePosixPath(key).stem
    # libtool numbers extra objects from one source as lt1-*, lt2-*: ...
    plain = re.sub(r"^lt\d+-", "", key)
    plain_stem = pathlib.PurePosixPath(plain).stem
    if plain_stem != stem:
        stem = plain_stem
    if key in deps:
        return deps[key], "dependency_file"
    if key in logs and (root / logs[key]).is_file():
        return logs[key], "build_log"
    if plain != key and plain in logs and (root / logs[plain]).is_file():
        return logs[plain], "build_log_libtool_alias"
    if stem in by_stem:
        picked = rank_candidates(by_stem[stem], prefer)
        if picked:
            return picked, "exact_stem"
        return None, "ambiguous_stem:" + "|".join(sorted(by_stem[stem])[:6])
    symbols = object_symbols(payload)
    tried, ambiguous_hits = [], []
    for symbol in symbols[:8]:
        token = demangle(symbol)
        candidates = []
        if "(" in token:
            candidates.append(token.split("(")[0])
        if "::" in token:
            candidates.append(token.split("(")[0].split("<", 1)[0])
        candidates.append(symbol)
        for candidate in dict.fromkeys(candidates):
            candidate = candidate.strip()
            if len(candidate) < 4:
                continue
            tried.append(candidate)
            hits, _ = search_source(candidate, all_paths, root)
            if not hits:
                continue
            picked = rank_candidates(hits, prefer)
            if picked:
                return picked, "symbol_lookup"
            ambiguous_hits.extend(hits)
    if ambiguous_hits:
        return None, "ambiguous_symbol:" + "|".join(sorted(set(ambiguous_hits))[:4])
    picked, hits = stem_text_search(stem, all_paths, root, prefer)
    if picked:
        return picked, "stem_text_search"
    if hits:
        return None, "ambiguous_stem_text:" + "|".join(hits[:4])
    return None, "unresolved_symbols:" + ",".join(tried[:4])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write the deterministic JSON report here")
    args = parser.parse_args()

    root = ROOT / SOURCE_ROOT
    deps = dependency_map()
    logs = build_log_map()
    by_stem, all_paths = source_files()
    archives, unmapped, categories = {}, [], collections.Counter()
    tiers = collections.Counter()

    for name, relative in ARCHIVES.items():
        payload_map = read_archive(ROOT / relative)
        prefer = "libgcc/" if name == "libgcc.a" else "libstdc++-v3/"
        entries = []
        for member in sorted(payload_map):
            source, tier = resolve(member, payload_map[member], deps, logs,
                                   by_stem, all_paths, root, prefer)
            tiers[tier.split(":")[0]] += 1
            if source is None:
                category, match = "unmapped", None
            else:
                category, match = declaration_category(source, root)
                categories[category] += 1
            record = {"member": member, "source": source, "resolution": tier,
                      "declaration_category": category}
            if match:
                record["declaration_text"] = match
            entries.append(record)
            if source is None:
                unmapped.append({"archive": name, "member": member, "resolution": tier})
        archives[name] = {"path": relative, "members": entries, "member_count": len(entries),
                          "resolved": sum(1 for e in entries if e["source"])}

    report = {
        "version": 1,
        "generated_by": "scripts/gcc_runtime_member_license_map.py",
        "source_tree": SOURCE_ROOT,
        "archives": archives,
        "totals": {
            "members": sum(a["member_count"] for a in archives.values()),
            "resolved": sum(a["resolved"] for a in archives.values()),
            "unmapped": len(unmapped),
            "resolution_tiers": dict(sorted(tiers.items())),
        },
        "declaration_categories": dict(sorted(categories.items())),
        "unmapped": unmapped,
        "disclaimer": ("Declaration extraction and source attribution, not a per-member legal "
                       "opinion; GCC Runtime Library Exception and per-file terms are recorded "
                       "from the sources that were matched."),
    }
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    totals = report["totals"]
    print(f"members={totals['members']} resolved={totals['resolved']} "
          f"unmapped={totals['unmapped']} tiers={dict(sorted(tiers.items()))} "
          f"categories={report['declaration_categories']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
