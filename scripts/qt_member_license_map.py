#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Map every Qt static archive member to its source file and declaration category.

The two QtBase 6.8.3 static build trees under ``build/qt6_b1_20261031`` are
enumerated member by member and resolved in tiers:

1. ``d_record`` - a retained AUTOMOC ``.d`` dependency record names the compiled
   source.  In this build the ``.d`` files only cover AUTOMOC outputs
   (``moc_*.cpp`` / ``*.moc``), so this tier rarely fires for archive members;
   it is kept because it is the literal dependency evidence.
2. ``object_record`` - the build tree retained the exact object that was
   archived (byte-identical).  Its ``CMakeFiles/<Target>.dir/...`` layout
   encodes the source path relative to the target source directory.  This is
   the tier that actually covers the archives here.
3. ``same_name_source`` - a source file with the same file name exists in the
   locked source tree; ambiguity is reported, never guessed.
4. ``symbol_lookup`` - the object's defined text symbols (``x86_64-elf-nm``)
   are demangled (``c++filt``) and searched for a unique source hit.

Generated inputs (AUTOMOC ``mocs_compilation.cpp``, RCC ``qrc_*.cpp``) have no
in-tree source; they resolve to their build-tree path and are flagged
``generated`` instead of being guessed back to a single header.

Declaration categories are extracted from the resolved file's header text.  They
are a *declaration extraction*, not a legal opinion; Qt's per-file terms stay in
the upstream ``LICENSES/`` texts and in ``src/ports/qt6/licenses/``.
"""
import argparse
import collections
import hashlib
import json
import pathlib
import posixpath
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ARCHIVE_TREES = {
    "widgets": "build/qt6_b1_20261031/widgets",
    "widgets2": "build/qt6_b1_20261031/widgets2",
}
BUILD_ROOT = "build/qt6_b1_20261031"
# The build's CMAKE_HOME_DIRECTORY and every retained .d record point at the
# -gui checkout; the plain and -b1 checkouts differ by only 5 / 2 files and
# carry the same 37 LICENSES texts.
SOURCE_TREE = ".cache/xos_seed/qt6/qtbase-6.8.3-gui"
SOURCE_TREE_SIBLINGS = (
    ".cache/xos_seed/qt6/qtbase-6.8.3",
    ".cache/xos_seed/qt6/qtbase-6.8.3-b1",
)
LICENSES_DIR = ".cache/xos_seed/qt6/qtbase-6.8.3-gui/LICENSES"
SOURCE_SUFFIXES = (".c", ".cc", ".cpp", ".h", ".hpp", ".S", ".s", ".mm")

# Qt branch: the GCC runtime "GCC Runtime Library Exception" rule does not
# apply to Qt, so it is replaced by the Qt-specific commercial reference and
# the remaining generic rules are kept in the gcc script's order.
DECLARATION_RULES = (
    ("commercial_reference", re.compile(
        r"SPDX-License-Identifier:[^\n]*LicenseRef-Qt-Commercial[^\n]*")),
    ("spdx", re.compile(r"SPDX-License-Identifier:[^\n]*")),
    ("lgpl", re.compile(r"GNU (Lesser|Library) General Public License|\bLGPL\b", re.I)),
    ("gpl", re.compile(r"GNU General Public License|\bGPL\b", re.I)),
    ("bsd_like", re.compile(r"Redistribution and use in source and binary forms", re.I)),
    ("mit_like", re.compile(r"Permission to use, copy, modify, and/or distribute", re.I)),
    ("other_copyright", re.compile(r"Copyright\s*(\(|©|\d)", re.I)),
)
SPDX_RE = re.compile(r"SPDX-License-Identifier:\s*(.+)")


def read_archive(path):
    """Return {member_name: bytes} for a GNU ``!<arch>`` archive, in file order."""
    data = Path(path).read_bytes()
    if data[:8] != b"!<arch>\n":
        raise SystemExit(f"not a plain ar archive: {path}")
    offset, longnames, out = 8, None, collections.OrderedDict()
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
            out[token.rstrip("/")] = chunk
        offset = body + size
        if offset % 2:
            offset += 1
    return out


def archive_target(archive_name):
    """``libQt6FbSupport.a`` -> ``FbSupport`` (the CMake target name stem)."""
    stem = archive_name[len("lib"):-len(".a")]
    if stem.startswith("Qt6"):
        stem = stem[len("Qt6"):]
    return stem


def object_index(tree_root):
    """basename -> [object paths] for every retained object of one build tree."""
    index = collections.defaultdict(list)
    for path in sorted(tree_root.rglob("*.o")):
        index[path.name].append(path)
    return index


def target_scoped_candidates(paths, target):
    """Objects whose CMake target directory belongs to ``target``."""
    marker = "/CMakeFiles/"
    hits = []
    for path in paths:
        parts = path.as_posix().split(marker, 1)
        if len(parts) != 2:
            continue
        target_dir = parts[1].split("/", 1)[0]
        if not target_dir.endswith(".dir"):
            continue
        stem = target_dir[:-len(".dir")]
        if stem == target or stem.startswith(target):
            hits.append(path)
    return hits


def prefer_candidate(hits, target):
    """Deterministic pick: exact target dir, then ``<target>Private``, then shortest."""
    if not hits:
        return None, []
    exact = [p for p in hits
             if f"/CMakeFiles/{target}.dir/" in p.as_posix()]
    pool = exact or hits
    if len(pool) == 1:
        return pool[0], []
    private = [p for p in pool
               if f"/CMakeFiles/{target}Private.dir/" in p.as_posix()]
    if len(private) == 1:
        return private[0], []
    pool = sorted(pool, key=lambda p: (len(p.as_posix()), p.as_posix()))
    if len(pool) > 1 and pool[0].as_posix() == pool[1].as_posix():
        return pool[0], []
    if len(pool) > 1 and len({p.name for p in pool}) == 1:
        # Same object name in two target dirs of the same target stem: the
        # shortest path is still ambiguous, report it.
        return None, sorted(p.as_posix() for p in pool)
    if len(pool) > 1:
        return None, sorted(p.as_posix() for p in pool)
    return pool[0], []


def source_from_object(tree_root, object_path, target):
    """Derive the source path encoded by a ``CMakeFiles/<Target>.dir/`` object."""
    relative = object_path.relative_to(tree_root).as_posix()
    marker = "CMakeFiles/"
    head, _, tail = relative.partition(marker)
    if not tail:
        return None
    _, _, rest = tail.partition("/")
    if not rest:
        return None
    # head = "src/corelib/", rest = "kernel/qwidget.cpp.o" or
    # "Core_autogen/mocs_compilation.cpp.o"
    rest = rest[:-len(".o")] if rest.endswith(".o") else rest
    joined = head + rest
    normalized = "/".join(
        ".." if part == "__" else part for part in joined.split("/"))
    return posixpath.normpath(normalized)


def dependency_index(build_root):
    """AUTOMOC ``.d`` records: target file name -> its in-tree path."""
    mapping = {}
    for dep in sorted(build_root.rglob("*.d")):
        try:
            text = dep.read_text(errors="replace")
        except OSError:
            continue
        first = text.split(":", 1)[0].strip()
        if first:
            mapping.setdefault(pathlib.PurePosixPath(first).name, dep.parent)
    return mapping


def source_index(source_root):
    """file name -> [source-relative paths] in the locked source tree."""
    index = collections.defaultdict(list)
    if not source_root.is_dir():
        return index
    for path in sorted(source_root.rglob("*")):
        if path.is_file() and path.suffix in SOURCE_SUFFIXES:
            index[path.name].append(path.relative_to(source_root).as_posix())
    return index


def read_text(path):
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def read_source_body(source_root, source):
    """Read a resolved source; build-tree generated inputs are repo-relative."""
    if not source:
        return ""
    candidate = ROOT / source if source.startswith(BUILD_ROOT + "/") else source_root / source
    return read_text(candidate)


def declaration_category(body):
    """Category plus matched text for one source body (whole file, gcc order)."""
    if not body:
        return "no_declaration", None
    for category, pattern in DECLARATION_RULES:
        match = pattern.search(body)
        if match:
            return category, match.group(0).strip()
    if re.search(r"copyright", body, re.I):
        return "other_copyright", None
    return "no_declaration", None


def spdx_expression(body):
    match = SPDX_RE.search(body) if body else None
    return match.group(1).strip() if match else None


def object_payload_symbols(payload):
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
        if len(parts) >= 3 and parts[1] in ("T", "t"):
            symbols.append(parts[-1])
    return symbols


def demangle(symbol):
    try:
        result = subprocess.run(["c++filt", symbol], capture_output=True,
                                text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return symbol
    text = result.stdout.strip()
    return text if text else symbol


def search_source(token, all_paths, source_root):
    """Unique source file containing ``token``; never guesses between hits."""
    if not token or len(token) < 4:
        return []
    hits = []
    for relative in all_paths:
        if token in read_text(source_root / relative):
            hits.append(relative)
            if len(hits) > 12:
                break
    return hits


def symbol_lookup(payload, all_paths, source_root):
    tried = []
    for symbol in object_payload_symbols(payload)[:8]:
        token = demangle(symbol)
        candidates = [token]
        if "(" in token:
            head = token.split("(")[0]
            candidates.append(head)
            if "::" in head:
                candidates.append(head.split("<", 1)[0])
        candidates.append(symbol)
        for candidate in candidates:
            candidate = candidate.strip()
            if len(candidate) < 4:
                continue
            tried.append(candidate)
            hits = search_source(candidate, all_paths, source_root)
            if len(hits) == 1:
                return hits[0], "symbol_lookup"
            if len(hits) > 1:
                return None, "ambiguous_symbol:" + "|".join(sorted(hits)[:4])
    return None, "unresolved_symbols:" + ",".join(tried[:4])


def resolve(member, payload, deps, objects, target, source_root, source_idx,
            all_paths, use_object_record=True):
    """Resolve one member to (source_relative_or_None, resolution, generated)."""
    source_name = member[:-2] if member.endswith(".o") else member

    # Tier 1a: retained AUTOMOC .d record naming this exact source.  In this
    # build the .d files only cover moc_*.cpp / *.moc targets, so they rarely
    # name an archive member; the tier stays because it is the literal
    # dependency evidence.
    if source_name in deps:
        candidate = deps[source_name] / source_name
        if candidate.is_file():
            return candidate.relative_to(ROOT).as_posix(), "d_record", True

    # Tier 1b: byte-identical retained object whose path encodes the source.
    if use_object_record:
        hits = target_scoped_candidates(objects.get(member, []), target)
        chosen, ambiguous_paths = prefer_candidate(hits, target)
        if chosen is not None:
            derived = source_from_object(parent_of_target(chosen), chosen, target)
            if derived:
                if (source_root / derived).is_file():
                    return derived, "object_record", False
                build_copy = tree_of(chosen) / derived
                if build_copy.is_file():
                    return build_copy.relative_to(ROOT).as_posix(), "object_record", True
                return None, "object_record_missing_source:" + derived, False
        if ambiguous_paths:
            return None, "ambiguous_object:" + "|".join(ambiguous_paths[:4]), False

    # Tier 2: unique same-named source file.
    candidates = sorted(source_idx.get(source_name, []))
    if len(candidates) == 1:
        return candidates[0], "same_name_source", False
    if len(candidates) > 1:
        return None, "ambiguous_stem:" + "|".join(candidates[:6]), False

    # Tier 3: symbol reverse lookup.
    found, note = symbol_lookup(payload, all_paths, source_root)
    return found, note, False


def parent_of_target(object_path):
    """Build-tree root that owns this object (``.../widgets`` or ``.../widgets2``)."""
    parts = object_path.parts
    marker = Path(BUILD_ROOT).parts[-1]  # "qt6_b1_20261031"
    for i, part in enumerate(parts):
        if part == marker and i + 1 < len(parts):
            return Path(*parts[:i + 2])
    raise SystemExit(f"object outside build tree: {object_path}")


def tree_of(object_path):
    return parent_of_target(object_path)


DECLARATION_WINDOW = 64  # header lines; beyond this a licence id is prose, not a declaration
DECLARATION_LINE = re.compile(
    r"copyright|licen[cs]e|SPDX|redistribution|permission (?:is |to |hereby)"
    r"|all rights reserved|warranty|disclaimer", re.I)


def declaration_header(source_root, source):
    """The declaration-looking lines of a source header (first window lines).

    Searching the whole header would count prose such as "many X11 server" or
    "On X11, the pixmap..." as a licence citation, so only lines that actually
    talk about copyright/licence/redistribution are kept.
    """
    body = read_source_body(source_root, source)
    lines = body.splitlines()[:DECLARATION_WINDOW]
    return "\n".join(line for line in lines if DECLARATION_LINE.search(line))


def component_attribution(source_root, source):
    """Primary ``qt_attribution.json`` LicenseIds for a bundled component.

    Bundled components under ``src/3rdparty/<name>/`` ship Qt's own
    ``qt_attribution.json``, which records the SPDX ``LicenseId`` of the
    component.  Only the entry whose ``Id`` names the component directory (or
    the sole entry when there is one) is used as the *primary* licence, so a
    component that bundles further third-party code (FreeType's zlib, PCRE2's
    sljit) never has that sub-licence attributed to all of its members.  The
    full candidate set is returned alongside for transparency.
    """
    if not source or "/3rdparty/" not in source:
        return set(), set()
    name = source.split("/3rdparty/", 1)[1].split("/", 1)[0]
    path = source_root / "src/3rdparty" / name / "qt_attribution.json"
    if not path.is_file():
        return set(), set()
    try:
        data = json.loads(read_text(path))
    except ValueError:
        return set(), set()
    entries = data if isinstance(data, list) else [data]
    ids = [str(e.get("LicenseId")) for e in entries
           if isinstance(e, dict) and e.get("LicenseId")]
    if not ids:
        return set(), set()
    def squashed(text):
        return re.sub(r"[^a-z0-9]+", "", text.lower())
    primary = [i for e, i in zip([e for e in entries
                                  if isinstance(e, dict) and e.get("LicenseId")], ids)
               if squashed(str(e.get("Id", ""))) == squashed(name)]
    if len(primary) == 1:
        chosen = primary
    elif len(ids) == 1:
        chosen = ids
    else:
        return set(), {token for i in ids for token in re.split(
            r"\s+(?:OR|AND)\s+", i)}
    tokens = {token.strip() for i in chosen
              for token in re.split(r"\s+(?:OR|AND)\s+", i)}
    return tokens, {token.strip() for i in ids
                    for token in re.split(r"\s+(?:OR|AND)\s+", i)}


def license_text_correspondence(members, source_root, licenses_dir):
    """Map each upstream LICENSES/ text to the members that actually link it.

    Two independent signals, each scoped differently:

    * ``matched_by_spdx_expression`` - the member's own source records the id
      in its ``SPDX-License-Identifier`` line (file-level claim).
    * ``matched_by_declaration_header`` - a declaration-looking header line of
      the member's source names the id as a whole word (file-level claim).
    * ``matched_by_component_attribution`` - the member comes from a bundled
      component whose ``qt_attribution.json`` primary ``LicenseId`` is this id
      (component-level claim; see ``component_attribution``).

    Word-window prose matching was tried and rejected: it claimed HPND for
    HarfBuzz and BSD-4-Clause for double-conversion, so it is not used here.
    """
    texts = sorted(p for p in licenses_dir.glob("*.txt")) if licenses_dir.is_dir() else []
    headers, attribution, candidates = {}, {}, {}
    for record in members:
        source = record.get("source")
        if not source or record.get("generated") or source in headers:
            continue
        headers[source] = declaration_header(source_root, source)
        attribution[source], candidates[source] = component_attribution(
            source_root, source)
    out = []
    for path in texts:
        spdx_id = path.stem
        pattern = re.compile(
            r"(?<![A-Za-z0-9-])" + re.escape(spdx_id) + r"(?![A-Za-z0-9-])")
        by_expression, by_header, by_attribution = set(), set(), set()
        for record in members:
            if record.get("generated"):
                continue
            source = record.get("source")
            if pattern.search(record.get("spdx_expression") or ""):
                by_expression.add(source)
            header = headers.get(source)
            if header and pattern.search(header):
                by_header.add(source)
            if spdx_id in attribution.get(source, set()):
                by_attribution.add(source)
        all_sources = by_expression | by_header | by_attribution
        out.append({
            "text": path.name,
            "spdx_id": spdx_id,
            "matched_sources": len(all_sources),
            "matched_by_spdx_expression": len(by_expression),
            "matched_by_declaration_header": len(by_header - by_expression),
            "matched_by_component_attribution": len(
                by_attribution - by_expression - by_header),
            "corresponds_to_linked_members": bool(all_sources),
            "example_sources": sorted(all_sources)[:4],
        })
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path,
                        help="write the deterministic JSON report here")
    parser.add_argument("--no-object-record", action="store_true",
                        help="skip tier 1b to exercise the name/symbol tiers")
    args = parser.parse_args()
    use_object_record = not args.no_object_record

    source_root = ROOT / SOURCE_TREE
    licenses_dir = ROOT / LICENSES_DIR
    deps = {}
    source_idx = source_index(source_root)
    all_paths = sorted(p for names in source_idx.values() for p in names)

    archives, unmapped, ambiguous = {}, [], []
    categories = collections.Counter()
    tiers = collections.Counter()
    expressions = collections.Counter()
    generated_total = 0
    identical_total = 0
    all_members = []
    attribution_cache = {}

    for tree_name, tree_rel in sorted(ARCHIVE_TREES.items()):
        tree_root = ROOT / tree_rel
        if not tree_root.is_dir():
            raise SystemExit(f"missing build tree: {tree_rel}")
        if not deps:
            deps = dependency_index(ROOT / BUILD_ROOT)
        objects = object_index(tree_root)
        for archive in sorted((tree_root / "lib").glob("*.a")):
            target = archive_target(archive.name)
            entries = []
            for member, payload in read_archive(archive).items():
                source, resolution, generated = resolve(
                    member, payload, deps, objects, target, source_root,
                    source_idx, all_paths, use_object_record)
                tier = resolution.split(":")[0]
                tiers[tier] += 1
                object_hits = target_scoped_candidates(
                    objects.get(member, []), target)
                byte_identical = False
                if object_hits:
                    chosen, _ = prefer_candidate(object_hits, target)
                    if chosen is not None:
                        byte_identical = chosen.read_bytes() == payload
                        if byte_identical:
                            identical_total += 1
                if generated:
                    generated_total += 1
                body = read_source_body(source_root, source)
                if source is None:
                    category, match, expression = "unmapped", None, None
                else:
                    category, match = declaration_category(body)
                    expression = spdx_expression(body)
                    categories[category] += 1
                    if expression:
                        expressions[expression] += 1
                record = {
                    "member": member,
                    "source": source,
                    "resolution": resolution,
                    "declaration_category": category,
                    "generated": bool(generated),
                    "byte_identical_object": byte_identical,
                }
                if source and not generated:
                    if source not in attribution_cache:
                        attribution_cache[source] = component_attribution(
                            source_root, source)
                    primary, candidates = attribution_cache[source]
                    if primary:
                        record["component_license_ids"] = sorted(primary)
                    elif candidates:
                        record["component_license_candidates"] = sorted(candidates)
                if match:
                    record["declaration_text"] = match
                if expression:
                    record["spdx_expression"] = expression
                entries.append(record)
                all_members.append(record)
                if source is None:
                    (ambiguous if tier.startswith("ambiguous")
                     else unmapped).append({
                         "archive": f"{tree_name}/{archive.name}",
                         "member": member, "resolution": resolution})
            relative = f"{tree_rel}/lib/{archive.name}"
            archives[f"{tree_name}/{archive.name}"] = {
                "path": relative,
                "target": target,
                "member_count": len(entries),
                "resolved": sum(1 for e in entries if e["source"]),
                "generated": sum(1 for e in entries if e["generated"]),
                "members": entries,
            }

    correspondence = license_text_correspondence(
        all_members, source_root, licenses_dir)

    report = {
        "version": 1,
        "generated_by": "scripts/qt_member_license_map.py",
        "object_record_tier_enabled": use_object_record,
        "source_tree": SOURCE_TREE,
        "source_tree_siblings": list(SOURCE_TREE_SIBLINGS),
        "licenses_dir": LICENSES_DIR,
        "license_text_count": len(correspondence),
        "archive_trees": {name: rel for name, rel in sorted(ARCHIVE_TREES.items())},
        "archives": archives,
        "totals": {
            "members": sum(a["member_count"] for a in archives.values()),
            "resolved": sum(a["resolved"] for a in archives.values()),
            "generated_sources": generated_total,
            "byte_identical_objects": identical_total,
            "unmapped": len(unmapped),
            "ambiguous": len(ambiguous),
            "resolution_tiers": dict(sorted(tiers.items())),
            "license_texts_corresponded": sum(
                1 for c in correspondence if c["corresponds_to_linked_members"]),
            "license_texts_total": len(correspondence),
        },
        "declaration_categories": dict(sorted(categories.items())),
        "spdx_expressions": dict(sorted(expressions.items())),
        "license_text_correspondence": correspondence,
        "unmapped": unmapped,
        "ambiguous": ambiguous,
        "disclaimer": (
            "Member -> source -> declaration-category mapping and upstream license "
            "text correspondence only. This is not a legal opinion, grants no "
            "redistribution eligibility, and does not replace the LGPL-3.0-only / "
            "GPL obligations described in docs/reports/qt_static_distribution_20261103/. "
            "The repository holds no Qt commercial licence evidence, so every "
            "commercial path is N/A."
        ),
    }
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    totals = report["totals"]
    print(f"members={totals['members']} resolved={totals['resolved']} "
          f"generated={totals['generated_sources']} "
          f"unmapped={totals['unmapped']} ambiguous={totals['ambiguous']} "
          f"tiers={dict(sorted(tiers.items()))} "
          f"categories={report['declaration_categories']} "
          f"license_texts_matched="
          f"{sum(1 for c in correspondence if c['corresponds_to_linked_members'])}"
          f"/{len(correspondence)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
