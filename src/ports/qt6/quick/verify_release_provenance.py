#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify a recorded Qt Quick provenance inventory against the packaged SDK."""

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys

from qt_rcc_object import embedded_resources
from relink import manifest_file, sha

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))
from archive_member_map import read_archive


def read_bound_inventory(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"Inventory SHA-256 mismatch for {path.name}")
    if path.suffix == ".gz":
        data = gzip.decompress(data)
    return json.loads(data)


def kit_archives(kit, prefixes, name_prefix=""):
    return {name_prefix + path.relative_to(kit).as_posix()
            for prefix in prefixes for path in (kit / prefix).rglob("*.a") if path.is_file()}


def verify_members(kit, archives, target_members=None):
    counts = Counter()
    target = target_members is not None
    for name, archive in archives.items():
        member_file = manifest_file(kit, name.removeprefix("link/kit/") if target else name)
        if sha(member_file) != archive["archive_sha256"]:
            raise ValueError(f"Kit archive SHA-256 mismatch for {name}")
        objects = read_archive(member_file)
        rows = archive["members"]
        selected = target_members[name] if target else set(objects)
        ordered = [member for member in objects if member in selected]
        if [row["name"] for row in rows] != ordered or set(ordered) != selected:
            raise ValueError(f"Archive member order or coverage differs for {name}")
        counts["archives"] += 1
        for row in rows:
            member = row["name"]
            data = objects[member]
            if hashlib.sha256(data).hexdigest() != row["member_sha256"]:
                raise ValueError(f"Archive member SHA-256 mismatch for {name}/{member}")
            counts["members"] += 1
            generation = row.get("generation")
            if generation is None:
                if target or row["source_kind"] == "generated":
                    raise ValueError(f"Generated member provenance missing for {name}/{member}")
                continue
            if not generation["source"]["present"]:
                replay = generation.get("replay", {})
                if (replay.get("status") != "byte_identical"
                        or replay["generated_object"]["sha256"] != row["member_sha256"]):
                    raise ValueError(f"Missing byte-identical source replay for {name}/{member}")
                counts["replay_matches"] += 1
            if generation["kind"] == "rcc":
                expected = {resource: entry["embedded"] for resource, entry in generation["details"]["entries"].items()}
                if expected != embedded_resources(data):
                    raise ValueError(f"Embedded resource paths or bytes differ for {name}/{member}")
                counts["resources"] += len(expected)
    return dict(counts)


def verify(kit, inventory, original):
    if inventory["format"] != "xos_qt_quick_release_provenance_v1":
        raise ValueError("Unsupported Qt Quick provenance format")
    kit_digest = sha(manifest_file(kit, "manifest.json"))
    if kit_digest != inventory["kit_manifest_sha256"]:
        raise ValueError("Qt Quick kit manifest SHA-256 mismatch")

    generators = 0
    for name, record in inventory["generators"].items():
        if "kit_path" in record:
            if sha(manifest_file(kit, record["kit_path"])) != record["sha256"]:
                raise ValueError(f"Packaged Qt generator SHA-256 mismatch for {name}")
            generators += 1

    installed_host = kit_archives(kit, ("host_qt", "host_qml"))
    host = inventory["host"]["archives"]
    if installed_host != host.keys():
        raise ValueError("Host static archive scope differs from the provenance inventory")

    original_targets = original["archives"]
    installed_target = kit_archives(kit, ("target",), "link/kit/")
    if installed_target != original_targets.keys():
        raise ValueError("Target static archive scope differs from the earlier kit inventory")
    expected = {}
    for path, record in original_targets.items():
        if sha(manifest_file(kit, path.removeprefix("link/kit/"))) != record["archive_sha256"]:
            raise ValueError(f"Original kit archive SHA-256 mismatch for {path}")
        names = {row["name"] for row in record["members"] if row["source_kind"] == "generated"}
        if names:
            expected[path] = names
    target = inventory["target"]["archives"]
    if target.keys() != expected.keys():
        raise ValueError("Generated target archive coverage differs from the earlier inventory")
    return {"status": "passed", "kit_manifest_sha256": kit_digest, "packaged_generators": generators,
            "target": verify_members(kit, target, expected), "host": verify_members(kit, host)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("kit", "inventory", "target-members"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--inventory-sha256", required=True)
    args = parser.parse_args()
    inventory = read_bound_inventory(args.inventory, args.inventory_sha256)
    original = read_bound_inventory(args.target_members, inventory["prior_receipts"]["target_members_sha256"])
    print(json.dumps(verify(args.kit.resolve(strict=True), inventory, original), sort_keys=True))


if __name__ == "__main__":
    main()
