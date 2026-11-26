#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Capture Qt Quick's generated target members and Linux host static archives."""

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys

from audit_generated_members import GenerationAudit, cmake_setting, declared_license
from audit_static_members import archive_location, audit_archive_relative, ninja_edges
from relink import sha
from replay_qtbase_generated import GeneratedReplay

try:
    from archive_member_map import read_archive
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))
    from archive_member_map import read_archive


root_names = (
    "qtbase_source", "qtbase_target", "qtbase_host", "qtbase_target_prefix",
    "qtdeclarative_source", "qtdeclarative_target", "qtdeclarative_host",
    "qtshadertools_source", "qtshadertools_host",
)


def load_bound(path, expected):
    if sha(path) != expected:
        raise ValueError(f"Prior receipt digest differs for {path.name}")
    payload = path.read_bytes()
    if path.suffix == ".gz":
        payload = gzip.decompress(payload)
    return json.loads(payload)


def build_capture(source, build):
    if Path(cmake_setting(build, "CMAKE_HOME_DIRECTORY")).resolve() != source:
        raise ValueError("The CMake build record points to a different module source")
    return {"cmake_cache_sha256": sha(build / "CMakeCache.txt"),
            "ninja_record_sha256": sha(build / "build.ninja")}


def inspect_target(prior, roots, capture, replay):
    archives = {}
    prefix = "link/kit/target/"
    for location, entry in prior["archives"].items():
        selected = [row for row in entry["members"] if row["source_kind"] == "generated"]
        if not selected:
            continue
        if not location.startswith(prefix):
            raise ValueError("Target archive outside the kit target prefix")
        relative = location.removeprefix(prefix)
        module = entry["module"]
        if module not in {"qtbase", "qtdeclarative"}:
            raise ValueError("Unexpected Qt target source module")
        source = roots[module + "_source"]
        build = roots[module + "_target"]
        native = roots["qtbase_target_prefix"] if module == "qtbase" else build
        archive = archive_location(relative, entry["archive_sha256"], build, native)
        objects = read_archive(archive)
        rows = []
        for row in selected:
            data = objects[row["name"]]
            if hashlib.sha256(data).hexdigest() != row["member_sha256"]:
                raise ValueError("Archived generated member differs from the prior source record")
            details = capture.generated(row, build, source, data)
            if replay is not None and module == "qtbase" and not details["source"]["present"]:
                details["replay"] = replay.replay(row, details)
                if details["replay"]["status"] == "byte_identical" and details["kind"] == "automoc":
                    details["unresolved"].remove("exact_automoc_header_selection_unavailable")
            rows.append({**row, "generation": details})
        archives[location] = {"archive_sha256": entry["archive_sha256"], "module": module, "members": rows}
    return archives


def inspect_host(prior, roots, capture):
    archives = {}
    for location, entry in prior.items():
        if entry["type"] != "static_archive":
            continue
        if not location.startswith("host_qt/") or entry["component"] not in {"qtbase", "qtshadertools"}:
            raise ValueError("Unexpected host static archive scope")
        relative = location.removeprefix("host_qt/")
        module = entry["component"]
        source, build = (roots[module + "_" + suffix] for suffix in ("source", "host"))
        actual = archive_location(relative, entry["sha256"], build, roots["qtbase_host"])
        objects = read_archive(actual)
        ledger = {"archive_sha256": entry["sha256"],
                  "members": [{"name": name, "sha256": hashlib.sha256(data).hexdigest()}
                              for name, data in objects.items()]}
        rows = audit_archive_relative(relative, ledger, source, build, roots["qtbase_host"], ninja_edges(build))
        for row in rows:
            if row["source_kind"] == "generated":
                row["generation"] = capture.generated(row, build, source, objects[row["name"]])
        archives[location] = {"archive_sha256": entry["sha256"], "module": module, "members": rows}
    return archives


def summarize(archives):
    rows = [row for archive in archives.values() for row in archive["members"]]
    generated = [row["generation"] for row in rows if "generation" in row]
    resources = [entry for member in generated if member["kind"] == "rcc"
                 for entry in member["details"]["entries"].values()]
    return {
        "archives": len(archives), "members": len(rows), "generation_types": dict(Counter(x["kind"] for x in generated)),
        "retained_objects_matched": sum(row["retained_object_matched"] for row in rows),
        "generated_sources_present": sum(row["source"]["present"] for row in generated),
        "replay_outcomes": dict(Counter(row["replay"]["status"] for row in generated if "replay" in row)),
        "direct_sources_without_declarations": sum(row["source_kind"] == "source" and not declared_license(row)
                                                  for row in rows),
        "embedded_resource_occurrences_matched": len(resources),
        "embedded_resource_declaration_evidence": dict(Counter(entry["declaration_evidence"] for entry in resources)),
        "embedded_shader_provenance": dict(Counter(entry["shader"]["status"] for entry in resources
                                                   if "shader" in entry)),
        "generation_issues": dict(Counter(issue for row in generated for issue in row["unresolved"])),
    }


def audit(args):
    roots = {name: getattr(args, name).resolve(strict=True) for name in root_names}
    host = load_bound(args.host_inventory, args.host_inventory_sha256)
    prior_target = load_bound(args.target_inventory, args.target_inventory_sha256)
    paths = (("qtbase", "target"), ("qtbase", "host"), ("qtdeclarative", "target"), ("qtshadertools", "host"))
    builds = {module + "_" + role: build_capture(roots[module + "_source"], roots[module + "_" + role])
              for module, role in paths}
    capture = GenerationAudit(roots, host["files"])
    replay = None
    if args.replay_output is not None:
        output = args.replay_output.resolve()
        if any(output.is_relative_to(root) for root in roots.values()):
            raise ValueError("Replay output must be outside the captured build/source roots")
        roots["replay_output"] = output
        replay = GeneratedReplay(capture, roots["qtbase_target"], output, args.target_compiler_sha256)
    target = inspect_target(prior_target, roots, capture, replay)
    host_archives = inspect_host(host["files"], roots, capture)
    return {"format": "xos_qt_quick_release_provenance_v1",
            "kit_manifest_sha256": host["kit_manifest_sha256"],
            "prior_receipts": {"target_members_sha256": args.target_inventory_sha256,
                               "host_files_sha256": args.host_inventory_sha256},
            "build_records": builds, "generators": capture.tools,
            "target": {"summary": summarize(target), "archives": target},
            "host": {"summary": summarize(host_archives), "archives": host_archives}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in (*root_names, "target_inventory", "host_inventory", "output"):
        parser.add_argument("--" + field.replace("_", "-"), required=True, type=Path)
    for field in ("target-inventory-sha256", "host-inventory-sha256"):
        parser.add_argument("--" + field, required=True)
    parser.add_argument("--replay-output", type=Path)
    parser.add_argument("--target-compiler-sha256")
    args = parser.parse_args()
    if bool(args.replay_output) != bool(args.target_compiler_sha256):
        parser.error("--replay-output and --target-compiler-sha256 must be supplied together")
    result = audit(args)
    with args.output.open("x") as output:
        json.dump(result, output, indent=2, sort_keys=True, ensure_ascii=False)
        output.write("\n")
    print(json.dumps({section: result[section]["summary"] for section in ("target", "host")}))


if __name__ == "__main__":
    main()
