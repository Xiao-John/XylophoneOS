#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build static target QtQml and QtQuick from the locked Qt Declarative release."""

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile

from quick_kit import ROOT, PORT, kit_paths, verify_kit
from relink import sha

sys.path.insert(0, str(ROOT / "scripts"))
from glibc_g1_probe import clean_build_environment, tool_identity
from xypm_sdk_profile import verify_profile


qml = PORT.parent / "qml"
patches = (qml / "patches/xos_qv4_vm.patch", qml / "patches/xos_qv4_stacks.patch")
allocator = qml / "runtime/os_allocator_xos.cpp"
archives = ("libQt6Qml.a", "libQt6Quick.a")


def prepare_source(archive, root, version, env):
    prefix = f"qtdeclarative-everywhere-src-{version}"
    with tarfile.open(archive, "r:xz") as release:
        for item in release:
            path = PurePosixPath(item.name)
            if (path.parts[:1] != (prefix,) or ".." in path.parts
                    or not (item.isfile() or item.isdir())):
                raise ValueError(f"Unexpected Qt Declarative source member {item.name}")
            release.extract(item, root, filter="data")
    source = root / prefix
    for patch in patches:
        subprocess.run(["patch", "--batch", "--forward", "-p1", "-i", str(patch)],
                       cwd=source, check=True, env=env)
    shutil.copyfile(allocator, source / "src/3rdparty/masm/wtf/os_allocator_xos.cpp")
    return source


def rebuild(args):
    kit, archive = (path.resolve(strict=True) for path in (args.kit, args.source_archive))
    output = args.output.resolve()
    if output.is_relative_to(kit) or args.output.is_symlink():
        raise ValueError("Choose a new output outside the Qt Quick kit")
    lock = json.loads((qml / "source_lock.json").read_text())
    source_digest = sha(archive)
    if source_digest != lock["sha256"]:
        raise ValueError("Qt Declarative release archive differs from the source lock")
    kit_digest = verify_kit(kit)
    paths = kit_paths(kit)
    sdk = paths["sdk_build"]
    profile = json.loads(paths["sdk_profile"].read_text())
    binding = verify_profile(profile, "glibc", sdk)
    manifest = json.loads((sdk / "manifest.json").read_text())
    tools = {name: tool_identity(f"x86_64-elf-{name}") for name in ("gcc", "g++", "as", "ld", "ar", "ranlib")}
    if any(tool.get("sha256") != manifest["tools"][f"x86_64-elf-{name}"]["sha256"]
           for name, tool in tools.items()):
        raise ValueError("Cross tools differ from the kit's SDK manifest")

    env, _ = clean_build_environment(os.environ)
    for name in ("CMAKE_PREFIX_PATH", "Qt6_DIR", "Qt6_ROOT", "QML_IMPORT_PATH", "QML2_IMPORT_PATH",
                 "QT_ADDITIONAL_PACKAGES_PREFIX_PATH", "QT_ADDITIONAL_HOST_PACKAGES_PREFIX_PATH"):
        env.pop(name, None)
    env["LC_ALL"] = "C"

    output.mkdir(parents=True, exist_ok=False)
    binutils = output / "binutils"
    binutils.mkdir()
    for name in ("as", "ld"):
        (binutils / name).symlink_to(tools[name]["path"])
    recipe_digests = {path.name: sha(path) for path in (*patches, allocator)}
    source = prepare_source(archive, output / "source", lock["version"], env)
    prefix = paths["target_prefix"]
    host_qt = paths["host_qt"]
    host_qml = paths["host_qml"]
    packages = prefix / "lib/cmake"
    build = output / "build"
    includes = ";".join(profile["sdk_binding"]["cxx_runtime"]["include_directories"])
    subprocess.run([
        "cmake", "-S", str(source), "-B", str(build), "-G", "Ninja",
        "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        "-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF", "-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF",
        f"-DCMAKE_INSTALL_PREFIX={output / 'prefix'}",
        f"-DCMAKE_TOOLCHAIN_FILE={packages / 'Qt6/qt.toolchain.cmake'}",
        f"-DQT_CHAINLOAD_TOOLCHAIN_FILE={PORT.parent / 'glibc/glibc_toolchain.cmake'}",
        f"-DQt6_DIR:PATH={packages / 'Qt6'}",
        f"-DQT_HOST_PATH={host_qt}", f"-DQT_ADDITIONAL_HOST_PACKAGES_PREFIX_PATH={host_qml}",
        f"-DQt6QmlTools_DIR:PATH={host_qml / 'lib/cmake/Qt6QmlTools'}",
        f"-DQt6ShaderToolsTools_DIR:PATH={host_qt / 'lib/cmake/Qt6ShaderToolsTools'}",
        f"-DXOS_GLIBC_SDK={sdk / 'sysroot'}", f"-DXOS_GLIBC_TOOLS={binutils}",
        f"-DXOS_GLIBC_CXX_INCLUDES={includes}", f"-DXOS_SOURCE_ROOT={ROOT}",
        f"-DXOS_GLIBC_CC={tools['gcc']['path']}", f"-DXOS_GLIBC_CXX={tools['g++']['path']}",
        f"-DXOS_GLIBC_AR={tools['ar']['path']}", f"-DXOS_GLIBC_RANLIB={tools['ranlib']['path']}",
        "-DBUILD_SHARED_LIBS=OFF", "-DQT_BUILD_EXAMPLES=OFF", "-DQT_BUILD_TESTS=OFF",
        "-DFEATURE_qml_jit=OFF", "-DFEATURE_qml_debug=OFF", "-DFEATURE_qml_worker_script=OFF",
    ], check=True, env=env)
    subprocess.run(["cmake", "--build", str(build), "--parallel", str(args.jobs), "--target", "Qml", "Quick"],
                   check=True, env=env)
    if (sha(archive) != source_digest or verify_kit(kit) != kit_digest
            or verify_profile(json.loads(paths["sdk_profile"].read_text()), "glibc", sdk) != binding
            or any(sha(Path(tool["path"])) != tool["sha256"] for tool in tools.values())
            or any(sha(path) != recipe_digests[path.name] for path in (*patches, allocator))):
        raise RuntimeError("A source, recipe, tool or kit input changed during the build")

    outputs = {}
    for name in archives:
        rebuilt = build / "lib" / name
        with rebuilt.open("rb") as file:
            if file.read(8) != b"!<arch>\n":
                raise ValueError(f"{name} is not a static archive")
        digest = sha(rebuilt)
        kit_library = sha(prefix / "lib" / name)
        outputs[name] = {"sha256": digest, "bytes": rebuilt.stat().st_size,
                         "kit_sha256": kit_library, "matches_kit": digest == kit_library}
    receipt = {"status": "static_qtdeclarative_built", "source_sha256": source_digest,
               "recipe_sha256": recipe_digests, "kit_manifest_sha256": kit_digest,
               "sdk_manifest_sha256": profile["sdk_binding"]["sdk_manifest_sha256"],
               "target_tools": {name: tool["sha256"] for name, tool in tools.items()}, "archives": outputs}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("kit", "source-archive", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    rebuild(args)


if __name__ == "__main__":
    main()
