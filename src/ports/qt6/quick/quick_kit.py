#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage and verify a relocatable XOS Qt Quick development kit."""

import argparse
import os
from pathlib import Path
import platform
import re
import shutil
import sys

PORT = Path(__file__).resolve().parent
ROOT = PORT.parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from package_glibc_sdk import package_sdk
from xypm_format import canonical, load_json, require, sha_file
from xypm_sdk_profile import metadata_snapshot, relative_file, sdk_snapshot

QT_ROOT = PORT.parent
HOST_TOOLS = ("moc", "rcc", "qmlimportscanner", "qmltyperegistrar", "qmlcachegen")
MODULES = (
    "Core", "Gui", "Qml", "QmlMeta", "QmlModels", "Quick", "BundledPcre2",
    "BundledZLIB", "BundledFreetype", "BundledHarfbuzz",
)
NOTICE_PORTS = (("qtbase", QT_ROOT), ("qtdeclarative", QT_ROOT / "qml"),
                ("qtshadertools", PORT))
HOST_EXPORTS = {"host_qt": ("Qt6CoreTools", "Qt6GuiTools"), "host_qml": ("Qt6QmlTools",)}


def relocate_host_tools(prefix, packages):
    location = re.compile(r'^([ \t]*IMPORTED_LOCATION_RELEASE )"/[^"\n]+/((?:bin|libexec)/[\w.+-]+)"$',
                          re.MULTILINE)
    for package in packages:
        export = relative_file(prefix, f"lib/cmake/{package}/{package}Targets.cmake")

        def relative_location(match):
            relative_file(prefix, match[2])
            return f'{match[1]}"${{CMAKE_CURRENT_LIST_DIR}}/../../../{match[2]}"'

        original = export.read_text()
        revised = location.sub(relative_location, original)
        if revised != original:
            export.write_text(revised)


def qt_inputs(target, host_qt, host_qml):
    expected = {name: target / "lib" / f"libQt6{name}.a" for name in MODULES}
    for name, directory in (
        ("qtquick2plugin", "QtQuick"), ("qmlplugin", "QtQml"),
        ("modelsplugin", "QtQml/Models"), ("quickwindow", "QtQuick/Window"),
    ):
        library = "quickwindowplugin" if name == "quickwindow" else name
        expected[name] = target / "qml" / directory / f"lib{library}.a"
    for tool in HOST_TOOLS:
        prefix = host_qt if tool in HOST_TOOLS[:2] else host_qml
        expected[tool] = prefix / "libexec" / tool
    return expected


def kit_paths(kit):
    return {
        "target_prefix": kit / "target",
        "host_qt": kit / "host_qt",
        "host_qml": kit / "host_qml",
        "qtbase": kit / "qtbase.tar.xz",
        "sdk_build": kit / "runtime/sdk",
        "sdk_profile": kit / "runtime/profile.json",
    }


def fingerprint(kit):
    inputs = kit_paths(kit)
    trees = {
        name: sdk_snapshot(kit / name)[0]
        for name in ("target", "host_qt", "host_qml", "runtime", "notices")
    }
    qtbase = load_json(QT_ROOT / "source_lock.json")
    archive = sha_file(relative_file(kit, "qtbase.tar.xz"))
    require(archive == qtbase["sha256"], "QtBase source archive SHA-256 mismatch")
    expected = qt_inputs(inputs["target_prefix"], inputs["host_qt"], inputs["host_qml"])
    files = {
        name: relative_file(kit, path.relative_to(kit).as_posix())
        for name, path in expected.items()
    }
    for name in HOST_TOOLS:
        with files[name].open("rb") as stream:
            header = stream.read(20)
        require(header[:7] == b"\x7fELF\x02\x01\x01" and header[18:20] == b"\xb7\x00"
                and os.access(files[name], os.X_OK), "expected a Linux AArch64 host generator: " + name)
    return {
        "format_version": 1,
        "host_platform": "linux-aarch64",
        "target_platform": "x86_64-xos",
        "qt_version": qtbase["version"],
        "qtbase_source_sha256": archive,
        "qt_inputs": {name: sha_file(path) for name, path in files.items()},
        "tree_sha256": trees,
        "sdk_manifest_sha256": sha_file(relative_file(kit, "runtime/sdk/manifest.json")),
        "sdk_profile_file_sha256": sha_file(relative_file(kit, "runtime/profile.json")),
    }


def verify_target_receipt(path, *, tree_sha256, sdk_manifest, sdk_profile, inputs):
    receipt, digest = metadata_snapshot(path)
    require(receipt.get("status") == "static_qt_quick_target_installed",
            "Provide the installed Qt Quick target build receipt")
    require(receipt.get("target_tree_sha256") == tree_sha256
            and receipt.get("sdk_manifest_sha256") == sdk_manifest
            and receipt.get("sdk_profile_file_sha256") == sdk_profile
            and receipt.get("target_inputs") == {name: value for name, value in inputs.items()
                                                 if name not in HOST_TOOLS}
            and all(receipt.get("native_generators", {}).get(tool) == inputs[tool] for tool in HOST_TOOLS),
            "Installed Qt Quick target or SDK differs from the target build receipt")
    return digest


def kit_target_receipt(kit, shape, application_receipt):
    wanted = application_receipt.get("target_receipt_sha256")
    path = kit / "target_receipt.json"
    if wanted is None and not path.exists() and not path.is_symlink():
        return
    digest = verify_target_receipt(
        relative_file(kit, path.name), tree_sha256=shape["tree_sha256"]["target"],
        sdk_manifest=shape["sdk_manifest_sha256"], sdk_profile=shape["sdk_profile_file_sha256"],
        inputs=shape["qt_inputs"])
    require(digest == wanted, "The Qt target receipt differs from the initial application link")
    shape["target_receipt_sha256"] = digest


def verify_kit(kit):
    require(sys.platform == "linux" and platform.machine() in ("aarch64", "arm64"),
            "the Qt Quick kit requires a Linux AArch64 host")
    manifest, digest = metadata_snapshot(relative_file(kit, "manifest.json"))
    source_receipt = relative_file(kit, "input_application_receipt.json")
    shape = fingerprint(kit)
    shape["input_application_receipt_sha256"] = sha_file(source_receipt)
    kit_target_receipt(kit, shape, load_json(source_receipt))
    require(manifest == shape, "Qt Quick kit content differs from its manifest")
    return digest


def stage_kit(args):
    output = args.output.absolute()
    prefixes = {
        "target": args.target_prefix.resolve(strict=True),
        "host_qt": args.host_qt.resolve(strict=True),
        "host_qml": args.host_qml.resolve(strict=True),
    }
    source_dirs = [*prefixes.values(), args.sdk_build.resolve(strict=True),
                   *(port / "licenses" for _, port in NOTICE_PORTS)]
    require(not any(output.resolve().is_relative_to(path) for path in source_dirs),
            "the Qt Quick kit output must be outside the input prefixes")
    source_trees = {name: sdk_snapshot(path)[0] for name, path in prefixes.items()}
    receipt, receipt_digest = metadata_snapshot(args.application_receipt)
    require(receipt.get("status") == "static_quick_application_linked",
            "provide a linked Qt Quick application receipt for these inputs")
    output.mkdir(parents=True, exist_ok=False)
    try:
        for name, path in prefixes.items():
            shutil.copytree(path, output / name, symlinks=True)
            require(sdk_snapshot(output / name)[0] == source_trees[name],
                    "the installed Qt prefix changed while staging the kit: " + name)
        for name, packages in HOST_EXPORTS.items():
            relocate_host_tools(output / name, packages)
        package_sdk(args.sdk_build, args.sdk_profile, output / "runtime")
        shutil.copyfile(args.qtbase, output / "qtbase.tar.xz")
        shutil.copyfile(args.application_receipt, output / "input_application_receipt.json")
        if args.target_receipt is not None:
            shutil.copyfile(args.target_receipt, output / "target_receipt.json")
        notices = output / "notices"
        for name, port in NOTICE_PORTS:
            component_dir = notices / name
            shutil.copytree(port / "licenses", component_dir / "licenses")
            shutil.copyfile(port / "source_lock.json", component_dir / "source_lock.json")
        manifest = fingerprint(output)
        require(all(receipt[key] == manifest[key]
                    for key in ("sdk_manifest_sha256", "qt_inputs", "qtbase_source_sha256")),
                "the staged Qt kit differs from the linked application receipt")
        require(sha_file(output / "input_application_receipt.json") == receipt_digest,
                "the linked application receipt changed while staging the kit")
        manifest["input_application_receipt_sha256"] = receipt_digest
        kit_target_receipt(output, manifest, receipt)
        (output / "manifest.json").write_bytes(canonical(manifest))
    except Exception:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("target-prefix", "host-qt", "host-qml", "qtbase", "sdk-build", "sdk-profile",
                  "application-receipt", "output"):
        parser.add_argument(f"--{field}", type=Path, required=True)
    parser.add_argument("--target-receipt", type=Path, help="record the independently built target prefix")
    args = parser.parse_args()
    stage_kit(args)
    print(args.output / "manifest.json")


if __name__ == "__main__":
    main()
