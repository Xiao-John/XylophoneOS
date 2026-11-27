#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage and verify the same-SDK Qt Widgets inputs for a Mobius receiver."""

import argparse
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

PORT = Path(__file__).resolve().parent
ROOT = PORT.parents[3]
QT = ROOT / "src/ports/qt6"
sys.path[:0] = [str(ROOT / "scripts"), str(QT / "quick")]

from build_app import extract_font, sha
from glibc_g1_probe import tool_identity
from xypm_format import canonical, load_json, require
from xypm_sdk_profile import metadata_snapshot, relative_file, sdk_snapshot, verify_profile

MODULES = ("Core", "Gui", "Widgets", "BundledFreetype", "BundledHarfbuzz", "BundledPcre2", "BundledZLIB")
TOOLS = ("moc", "rcc")


def installed_inputs(prefix, host):
    inputs = {module: relative_file(prefix, f"lib/libQt6{module}.a") for module in MODULES}
    return inputs | {name: relative_file(host, f"libexec/{name}") for name in TOOLS}


def installed_build(build, prefix, source, sdk):
    cache_path = build / "CMakeCache.txt"
    cache = dict(line.split("=", 1) for line in cache_path.read_text().splitlines()
                 if line and not line.startswith(("#", "//")) and "=" in line)
    require(cache.get("FEATURE_widgets:BOOL") == "ON"
            and cache.get("CMAKE_HOME_DIRECTORY:INTERNAL") == str(source)
            and cache.get("XOS_GLIBC_SDK:UNINITIALIZED") == str(sdk)
            and cache.get("CMAKE_INSTALL_PREFIX:PATH") == str(prefix),
            "Qt Widgets configuration must match the source, installed prefix and glibc sysroot")
    for name in MODULES:
        installed = relative_file(prefix, f"lib/libQt6{name}.a")
        require(sha(installed) == sha(relative_file(build, f"lib/{installed.name}")),
                f"Installed archive differs from the matching Qt Widgets build: {name}")
    return cache_path


def kit_paths(kit):
    return kit / "target", kit / "host_qt", kit / "DejaVuSans.ttf"


def fingerprint(kit):
    prefix, host, font = kit_paths(kit)
    relative_file(kit, font.name)
    return {"target_tree_sha256": sdk_snapshot(prefix)[0],
            "host_tree_sha256": sdk_snapshot(host)[0], "font_sha256": sha(font),
            "qt_inputs": {name: sha(path) for name, path in installed_inputs(prefix, host).items()}}


def verify_kit(kit, expected, sdk_manifest_sha256, profile_sha256):
    manifest, digest = metadata_snapshot(relative_file(kit, "manifest.json"), expected)
    require(manifest.get("format_version") == 1
            and manifest.get("sdk_manifest_sha256") == sdk_manifest_sha256
            and manifest.get("sdk_profile_file_sha256") == profile_sha256,
            "Widgets kit belongs to a different glibc SDK or profile")
    lock = load_json(QT / "source_lock.json")
    require(manifest.get("qt_version") == lock["version"]
            and manifest.get("qtbase_archive_sha256") == lock["sha256"],
            "Widgets kit names a different QtBase release")
    require(manifest["files"] == fingerprint(kit), "Widgets kit files differ from the manifest")
    return digest


def stage(args):
    sdk, build, prefix, source, host = (
        path.resolve(strict=True) for path in
        (args.sdk_build, args.qt_build, args.qt_prefix, args.qt_source, args.host_qt))
    output = args.output.absolute()
    require(not output.exists() and not output.is_symlink()
            and not any(output.resolve().is_relative_to(path) for path in (sdk, build, prefix, source, host)),
            "Use a new Widgets kit directory outside its inputs")
    profile = load_json(args.sdk_profile)
    binding = verify_profile(profile, "glibc", sdk)
    sdk_digest = profile["sdk_binding"]["sdk_manifest_sha256"]
    profile_digest = sha(args.sdk_profile)
    sdk_manifest, _ = metadata_snapshot(sdk / "manifest.json", sdk_digest)
    tools = {name: tool_identity(f"x86_64-elf-{name}").get("sha256")
             for name in ("gcc", "g++", "as", "ld", "ar", "ranlib")}
    require(all(digest == sdk_manifest["tools"][f"x86_64-elf-{name}"]["sha256"]
                for name, digest in tools.items()), "Target tools differ from the glibc SDK")
    cache = installed_build(build, prefix, source, sdk / "sysroot")
    cache_digest = sha(cache)
    source_digest = sdk_snapshot(source)[0]
    target_digest, host_digest = sdk_snapshot(prefix)[0], sdk_snapshot(host)[0]
    font = relative_file(source, "src/3rdparty/wasm/DejaVuSans.ttf")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        staged.mkdir()
        target_copy, host_copy, font_copy = kit_paths(staged)
        archive_digest = extract_font(args.qtbase, font_copy)
        require(sha(font_copy) == sha(font), "Widgets build used a different QtBase font")
        shutil.copytree(prefix, target_copy)
        shutil.copytree(host, host_copy)
        files = fingerprint(staged)
        require(files["target_tree_sha256"] == sdk_snapshot(prefix)[0] == target_digest
                and files["host_tree_sha256"] == sdk_snapshot(host)[0] == host_digest
                and sdk_snapshot(source)[0] == source_digest and sha(cache) == cache_digest
                and verify_profile(load_json(args.sdk_profile), "glibc", sdk) == binding
                and sha(args.sdk_profile) == profile_digest,
                "Widgets build or SDK inputs changed during staging")
        manifest = {
            "format_version": 1,
            "qt_version": load_json(QT / "source_lock.json")["version"],
            "qtbase_archive_sha256": archive_digest,
            "qtbase_prepared_tree_sha256": source_digest,
            "qt_build_cache_sha256": cache_digest,
            "sdk_manifest_sha256": sdk_digest,
            "sdk_profile_file_sha256": profile_digest,
            "target_tools": tools,
            "files": files,
        }
        (staged / "manifest.json").write_bytes(canonical(manifest))
        digest = sha(staged / "manifest.json")
        staged.rename(output)
    print(json.dumps({"widgets_kit_manifest_sha256": digest, "sdk_manifest_sha256": sdk_digest}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("sdk-build", "sdk-profile", "qt-build", "qt-prefix", "qt-source", "host-qt", "qtbase", "output"):
        parser.add_argument(f"--{option}", type=Path, required=True)
    stage(parser.parse_args())


if __name__ == "__main__":
    main()
