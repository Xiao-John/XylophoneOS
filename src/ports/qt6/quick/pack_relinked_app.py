#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pack the relinked Qt Quick example for a private XOS package disk."""

import argparse
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile

from relink import manifest_file, verified_manifest, verify_static_elf

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))
from xos_app import application_sdk_check, sdk_notices
from xypm_format import canonical, check_profile, pack_package, require, sha_file, strict_json
from xypm_sdk_profile import digest_value, metadata_snapshot

PACKAGE_ID = "xos.qt-quick-example"
EXECUTABLE = "usr/bin/qt-quick-example.elf"
PROFILE = "notices/runtime/profile.json"


def pack(materials, materials_sha256, relink_receipt, sdk, revision, output):
    materials = materials.resolve(strict=True)
    sdk = sdk.resolve(strict=True)
    require(not any(output.resolve().is_relative_to(path) for path in (materials, sdk)),
            "package output is inside its inputs")
    manifest, materials_digest = verified_manifest(materials, materials_sha256)

    def read_material(name):
        return metadata_snapshot(manifest_file(materials, name), manifest["files"][name]["sha256"])

    kit, kit_digest = read_material("link/kit_manifest.json")
    require(kit_digest == manifest["kit_manifest_sha256"], "materials refer to a different kit")
    reference, _ = read_material("link/application_receipt.json")
    profile, profile_digest = read_material(PROFILE)
    require(profile.get("runtime_family") == "glibc", "Qt Quick example requires a glibc profile")
    binding = application_sdk_check(sdk, profile)
    require(profile_digest == kit["sdk_profile_file_sha256"]
            and binding["sdk_manifest_sha256"] == kit["sdk_manifest_sha256"] == reference["sdk_manifest_sha256"],
            "SDK profile differs from the Qt Quick kit")
    runtime, _ = metadata_snapshot(sdk / "manifest.json", binding["sdk_manifest_sha256"])

    relink, relink_digest = metadata_snapshot(relink_receipt)
    require(relink["status"] == "static_quick_application_linked"
            and relink["elf"] == "quick_app.elf"
            and relink["materials_manifest_sha256"] == materials_digest
            and relink["kit_manifest_sha256"] == kit_digest == reference["kit_manifest_sha256"],
            "relink receipt refers to different build inputs")
    plan_name = "link/plan.json"
    plan_bytes = manifest_file(materials, plan_name).read_bytes()
    require(hashlib.sha256(plan_bytes).hexdigest() == manifest["files"][plan_name]["sha256"],
            "link plan changed during staging")
    plan = strict_json(plan_bytes)
    targets = {entry["file"] for entry in plan if isinstance(entry, dict)
               and entry["file"].startswith("link/kit/target/") and entry["file"].endswith(".a")}
    replacements = relink["replacement_archives"]
    require(isinstance(replacements, dict) and replacements.keys() <= targets,
            "relink receipt contains an unknown replacement")
    for name, digest in replacements.items():
        digest_value(digest, name)
    reference_match = relink["elf_sha256"] == reference["elf_sha256"]
    require(relink["matches_reference"] is reference_match and (replacements or reference_match),
            "relink receipt does not match the reference ELF")

    with tempfile.TemporaryDirectory(prefix="xos_quick_example_") as temporary:
        stage = Path(temporary)
        entries = []

        def add(source, name, role, expected=None):
            destination = stage / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            digest = sha_file(destination)
            require(expected is None or expected == digest, "package input differs from its receipt: " + name)
            entries.append({"path": name, "type": "file", "role": role,
                            "size": destination.stat().st_size, "sha256": digest})

        add(manifest_file(relink_receipt.parent, relink["elf"]), EXECUTABLE, "executable", relink["elf_sha256"])
        verify_static_elf(stage / EXECUTABLE)

        licenses = []
        qt_gui_notices = "recipes/xos/src/ports/qt6/licenses/gui/src/3rdparty/"
        for name, info in manifest["files"].items():
            prefix, _, rest = name.partition("/licenses/")
            if name.startswith(qt_gui_notices):
                suffix = "qtbase/gui/" + name.removeprefix(qt_gui_notices)
            elif prefix in ("notices/qtbase", "notices/qtdeclarative", "notices/qtshadertools") and rest:
                suffix = prefix.removeprefix("notices/") + "/" + rest
            elif name in ("recipes/xos/LICENSE", "recipes/xos/NOTICE"):
                suffix = "xos/" + Path(name).name
            else:
                continue
            target = f"usr/share/licenses/{PACKAGE_ID}/{suffix}"
            add(manifest_file(materials, name), target, "data", info["sha256"])
            licenses.append(target)

        for source, name in sdk_notices(sdk, profile, "cpp"):
            target = f"usr/share/licenses/{PACKAGE_ID}/sdk/{name}"
            add(source, target, "data", runtime["artifacts"][name])
            licenses.append(target)

        receipt_name = f"usr/share/{PACKAGE_ID}/build_receipt.json"
        receipt = stage / receipt_name
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_bytes(canonical({
            "scope": "private Qt Quick example",
            "relink_receipt_sha256": relink_digest,
            "relink": relink,
            "profile_sha256": profile_digest,
            "sdk_manifest_sha256": binding["sdk_manifest_sha256"],
        }))
        entries.append({"path": receipt_name, "type": "file", "role": "data",
                        "size": receipt.stat().st_size, "sha256": sha_file(receipt)})
        package = {
            "format_version": 1, "id": PACKAGE_ID, "upstream_version": "1.0", "revision": revision,
            "target_profile": profile["id"], "required_features": ["cxx_runtime", "heap", "static_tls", "stdio", "threads"],
            "runtime_dependencies": [], "files": sorted(entries, key=lambda entry: entry["path"]),
            "licenses": sorted(licenses), "build_receipt": {"path": receipt_name, "sha256": sha_file(receipt)},
            "source": "Verified Qt Quick release materials and external example recipes/application",
        }
        check_profile(package, profile)
        return pack_package(stage, package, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("materials", "receipt", "sdk", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-materials-sha256", required=True)
    parser.add_argument("--revision", required=True, type=int)
    args = parser.parse_args()
    try:
        result = pack(args.materials, args.expected_materials_sha256, args.receipt, args.sdk, args.revision, args.output)
    except (KeyError, OSError, TypeError, ValueError) as error:
        parser.exit(1, f"Qt Quick example: {error}\n")
    print(result["sha256"])


if __name__ == "__main__":
    main()
