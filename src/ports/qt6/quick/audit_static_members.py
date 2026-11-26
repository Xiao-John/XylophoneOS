#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bind shipped Qt archive members to original Ninja compile edges and notices."""

import argparse
from collections import Counter
import fnmatch
from functools import lru_cache
import json
from pathlib import Path, PurePosixPath
import re
import tomllib

from relink import sha


compiler_edge = re.compile(r"^(CXX|C|ASM)_COMPILER__")
declaration = re.compile(r"SPDX-License-Identifier:\s*([^\r\n]+)")
license_id = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]*\+?")


def ninja_edges(build):
    edges = {}
    for line in (build / "build.ninja").read_text().replace("$\n", "").splitlines():
        if not line.startswith("build "):
            continue
        name, separator, body = line[6:].partition(": ")
        if not separator or " " in name:
            continue
        rule, *inputs = re.split(r" (?:\|\|?|\|@) ", body, maxsplit=1)[0].split()
        if compiler_edge.match(rule) or "_STATIC_LIBRARY_LINKER__" in rule:
            edges[name] = (rule, inputs)
    return edges


@lru_cache(maxsize=None)
def path_digest(path):
    return sha(path)


@lru_cache(maxsize=None)
def read_attributions(path):
    contents = path.read_text()
    relaxed = False
    try:
        records = json.loads(contents)
    except json.JSONDecodeError as error:
        if not error.msg.startswith("Invalid control character"):
            raise
        # Some original Qt attribution strings contain literal tab characters.
        records = json.loads(contents, strict=False)
        relaxed = True
    return (records if isinstance(records, list) else [records]), relaxed


def attributed_notices(root, source):
    hits = []
    for area in source.parents:
        path = area / "qt_attribution.json"
        if path.is_file():
            records, relaxed = read_attributions(path)
            for record in records:
                directory = record.get("Path")
                if directory and not source.is_relative_to(area / directory):
                    continue
                files = record.get("Files")
                if isinstance(files, str):
                    files = [files]
                if files and not any(fnmatch.fnmatchcase(source.relative_to(area).as_posix(), entry)
                                     for entry in files):
                    continue
                notices = record.get("LicenseFiles", [])
                if isinstance(record.get("LicenseFile"), str):
                    notices = [record["LicenseFile"], *notices]
                for notice in dict.fromkeys(notices):
                    candidate = area / notice
                    if candidate.is_file() and candidate.resolve().is_relative_to(root):
                        hits.append({"declaration": record.get("LicenseId", record.get("License")),
                                     "attribution": path.relative_to(root).as_posix(),
                                     "attribution_uses_literal_control_character": relaxed,
                                     "text": candidate.relative_to(root).as_posix(),
                                     "text_sha256": path_digest(candidate)})
        if area == root:
            break
    return hits


@lru_cache(maxsize=None)
def reuse_document(path):
    with path.open("rb") as stream:
        return tomllib.load(stream).get("annotations", [])


@lru_cache(maxsize=None)
def reuse_pattern(pattern):
    atoms = {"**/": "(?:.*/)?", "**": ".*", "*": "[^/]*", "?": "[^/]"}
    parts = re.split(r"(\*\*/|\*\*|\*|\?)", pattern)
    return re.compile("".join(atoms.get(part, re.escape(part)) for part in parts))


def reuse_annotations(root, source):
    result = []
    for directory in source.parents:
        config = directory / "REUSE.toml"
        if config.is_file():
            relative = source.relative_to(directory).as_posix()
            for row in reuse_document(config):
                patterns = row["path"]
                if isinstance(patterns, str):
                    patterns = [patterns]
                selected = [pattern for pattern in patterns if reuse_pattern(pattern).fullmatch(relative)]
                if selected and "SPDX-License-Identifier" in row:
                    result.append({"record": config.relative_to(root).as_posix(), "sha256": path_digest(config),
                                   "patterns": selected, "precedence": row.get("precedence", "closest"),
                                   "declaration": row["SPDX-License-Identifier"]})
        if directory == root:
            break
    return result


def source_declarations(root, source):
    contents = source.read_text(errors="replace")
    sidecar = source.with_name(source.name + ".license")
    annotations = reuse_annotations(root, source)
    expressions = sorted({match.rstrip(" */\t") for match in declaration.findall(contents)})
    adjacent = None
    if sidecar.is_file():
        adjacent = {"path": sidecar.relative_to(root).as_posix(), "sha256": path_digest(sidecar),
                    "declarations": sorted({match.rstrip(" */\t")
                                            for match in declaration.findall(sidecar.read_text())})}
    applicable = [*expressions, *(item["declaration"] for item in annotations),
                  *((adjacent or {}).get("declarations", []))]
    ids = {token.removesuffix("+") for expression in applicable for token in license_id.findall(expression)
           if token not in {"AND", "OR", "WITH"}}
    texts = {}
    for identifier in sorted(ids):
        text = root / "LICENSES" / (identifier + ".txt")
        if text.is_file():
            texts[identifier] = path_digest(text)
    return {"source": source.relative_to(root).as_posix(), "source_sha256": path_digest(source),
            "spdx_declarations": expressions, "spdx_license_texts": texts,
            "spdx_without_module_license_text": sorted(ids - texts.keys()),
            "component_notices": attributed_notices(root, source), "reuse_annotations": annotations,
            "license_sidecar": adjacent}


def archive_location(relative, expected, root, prefix):
    paths = (root / relative, prefix / relative)
    matches = [path for path in paths if path.is_file() and path_digest(path) == expected]
    if not matches:
        raise ValueError(f"No exact originally built or installed archive for {relative}")
    return matches[0]


def audit_archive(name, entry, root, build, prefix, edges):
    relative = name.removeprefix("link/kit/target/")
    if relative == name:
        raise ValueError(f"Invalid target archive path {name}")
    return audit_archive_relative(relative, entry, root, build, prefix, edges)


def audit_archive_relative(relative, entry, root, build, prefix, edges):
    if PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts:
        raise ValueError(f"Invalid archive path {relative}")
    archive_location(relative, entry["archive_sha256"], build, prefix)
    _, objects = edges[relative]
    members = entry["members"]
    if [PurePosixPath(obj).name for obj in objects] != [member["name"] for member in members]:
        raise ValueError(f"Original Ninja link order does not match the ledger for {relative}")

    result = []
    for obj, member in zip(objects, members, strict=True):
        output = build / obj
        retained = output.is_file()
        if retained and path_digest(output) != member["sha256"]:
            raise ValueError(f"Retained member differs from the archived object {obj}")
        row = {"name": member["name"], "member_sha256": member["sha256"],
               "build_object": obj, "retained_object_matched": retained}
        rule, sources = edges[obj]
        if not compiler_edge.match(rule) or len(sources) != 1:
            raise ValueError(f"Expected one original compiler source for {obj}")
        source = (build / sources[0]).resolve()
        if source.is_relative_to(root):
            row.update(source_declarations(root, source))
            row["source_kind"] = "source"
        elif source.is_relative_to(build):
            row["source_kind"] = "generated"
            row["generated_source"] = source.relative_to(build).as_posix()
            if source.is_file():
                row["generated_source_sha256"] = path_digest(source)
        else:
            raise ValueError(f"Compiler source is outside the module source and build for {obj}")
        result.append(row)
    return result


def audit(args):
    ledger_digest = sha(args.ledger)
    if ledger_digest != args.ledger_sha256:
        raise ValueError("Target member ledger SHA-256 mismatch")
    ledger = json.loads(args.ledger.read_text())
    groups = {}
    for name in ("qtbase", "qtdeclarative"):
        roots = tuple(getattr(args, name + "_" + suffix).resolve(strict=True)
                      for suffix in ("source", "build", "prefix"))
        source, build, _ = roots
        cache = (build / "CMakeCache.txt").read_text().splitlines()
        if f"CMAKE_HOME_DIRECTORY:INTERNAL={source}" not in cache:
            raise ValueError(f"Source directory differs from the original CMake cache for {name}")
        groups[name] = (*roots, ninja_edges(build))

    archives = {}
    for name, entry in ledger.items():
        relative = name.removeprefix("link/kit/target/")
        owners = [module for module, (*_, edges) in groups.items() if relative in edges]
        if len(owners) != 1:
            raise ValueError(f"Expected one original CMake module for {relative}: {owners}")
        owner = owners[0]
        rows = audit_archive(name, entry, *groups[owner])
        archives[name] = {"archive_sha256": entry["archive_sha256"], "module": owner, "members": rows}

    rows = [row for archive in archives.values() for row in archive["members"]]
    counts = Counter(row["source_kind"] for row in rows)
    summary = {"archives": len(archives), "members": len(rows), "compiled_sources": counts["source"],
               "generated_sources": counts["generated"],
               "matching_retained_objects": sum(row["retained_object_matched"] for row in rows),
               "file_spdx_available": sum(bool(row.get("spdx_declarations")) for row in rows),
               "component_notice_available": sum(bool(row.get("component_notices")) for row in rows),
               "direct_sources_without_declaration_or_notice": sum(row["source_kind"] == "source"
                   and not (row["spdx_declarations"] or row["component_notices"]) for row in rows)}
    return {"status": "source_provenance_checked", "input_ledger_sha256": ledger_digest,
            "summary": summary, "archives": archives}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-sha256", required=True)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    for name in ("qtbase", "qtdeclarative"):
        for suffix in ("source", "build", "prefix"):
            parser.add_argument(f"--{name}-{suffix}", required=True, type=Path)
    args = parser.parse_args()
    report = audit(args)
    with args.output.open("x") as output:
        json.dump(report, output, indent=2, ensure_ascii=False)
        output.write("\n")
    print(json.dumps(report["summary"]))


if __name__ == "__main__":
    main()
