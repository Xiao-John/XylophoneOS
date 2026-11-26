#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build a static Qt Quick application against one installed XOS glibc Qt kit."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

PORT = Path(__file__).resolve().parent
QT_PORT = PORT.parent
ROOT = PORT.parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from build_glibc_program import sha, verify_elf
from glibc_g1_probe import clean_build_environment, tool_identity
from quick_kit import MODULES, kit_paths, qt_inputs, verify_kit, verify_target_receipt
from xypm_format import load_json
from xypm_sdk_profile import metadata_snapshot, sdk_snapshot, verify_profile


def extract_font(archive, font):
    lock = load_json(QT_PORT / "source_lock.json")
    if sha(archive) != lock["sha256"]:
        raise ValueError("QtBase source archive SHA-256 mismatch")
    member = f'qtbase-everywhere-src-{lock["version"]}/src/3rdparty/wasm/DejaVuSans.ttf'
    with tarfile.open(archive, "r|xz") as contents:
        for item in contents:
            if item.name == member and item.isfile():
                with contents.extractfile(item) as original:
                    font.write_bytes(original.read())
                return lock["sha256"]
    raise ValueError("The locked QtBase archive lacks the expected DejaVu font")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("source", "output"):
        parser.add_argument(f"--{field}", type=Path, required=True)
    for field in ("target-prefix", "host-qt", "host-qml", "qtbase", "sdk-build", "sdk-profile"):
        parser.add_argument(f"--{field}", type=Path)
    parser.add_argument("--kit", type=Path, help="use a kit staged by quick_kit.py")
    parser.add_argument("--target-receipt", type=Path, help="prove the separate target prefix was built with this SDK")
    parser.add_argument("--target", required=True, help="CMake executable target and ELF basename")
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if args.jobs < 1 or not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_-]*", args.target):
        parser.error("--jobs must be positive and --target must be a CMake executable name")
    kit_digest = None
    if args.kit is not None:
        kit = args.kit.resolve(strict=True)
        paths = kit_paths(kit)
        if args.target_receipt is not None or any(getattr(args, field) is not None for field in paths):
            parser.error("--kit cannot be combined with separate Qt and glibc SDK inputs")
        if args.output.resolve().is_relative_to(kit):
            parser.error("The output must be outside the staged kit")
        kit_digest = verify_kit(kit)
        if (kit / "target_receipt.json").is_file():
            args.target_receipt = kit / "target_receipt.json"
        for field, path in paths.items():
            setattr(args, field, path)
    elif any(getattr(args, field) is None for field in kit_paths(Path("."))):
        parser.error("Specify --kit or all separate Qt and glibc SDK inputs")
    if args.output.exists() or args.output.is_symlink() or args.sdk_build.is_symlink():
        parser.error("Use a fresh output path and an SDK build directory")

    output = args.output.resolve()
    source, prefix, host_qt, host_qml, sdk_build = (
        path.resolve(strict=True) for path in
        (args.source, args.target_prefix, args.host_qt, args.host_qml, args.sdk_build))
    if any(output.is_relative_to(path) for path in (source, prefix, host_qt, host_qml, sdk_build)):
        parser.error("The output must be outside the source, Qt prefixes and SDK")
    if not (source / "CMakeLists.txt").is_file():
        parser.error("The source must be a CMake application")

    profile = load_json(args.sdk_profile)
    binding = verify_profile(profile, "glibc", sdk_build)
    if (not {"cxx_runtime", "threads"} <= set(profile["features"])
            or "usr/lib/libxos_terminal.a" not in profile["sdk_binding"]["link_artifacts"]):
        parser.error("The glibc candidate must bind C++, threads and the XOS terminal runtime")
    sdk_manifest = profile["sdk_binding"]["sdk_manifest_sha256"]
    manifest, _ = metadata_snapshot(sdk_build / "manifest.json", sdk_manifest)
    tools = {name: tool_identity(f"x86_64-elf-{name}")
             for name in ("gcc", "g++", "as", "ld", "ar", "ranlib")}
    for name, tool in tools.items():
        if tool.get("sha256") != manifest["tools"][f"x86_64-elf-{name}"]["sha256"]:
            parser.error(f"x86_64-elf-{name} differs from the SDK build")

    expected = qt_inputs(prefix, host_qt, host_qml)
    for path in expected.values():
        if not path.is_file() or path.resolve(strict=True) != path:
            parser.error(f"Missing or redirected Qt kit input: {path}")
    input_digests = {name: sha(path) for name, path in expected.items()}
    target_digest = source_digest = None
    if args.target_receipt:
        target_digest = verify_target_receipt(
            args.target_receipt, tree_sha256=sdk_snapshot(prefix)[0], sdk_manifest=sdk_manifest,
            sdk_profile=sha(args.sdk_profile), inputs=input_digests)
        source_digest = sdk_snapshot(source)[0]

    env, _ = clean_build_environment(os.environ)
    for variable in ("CMAKE_PREFIX_PATH", "Qt6_DIR", "Qt6_ROOT", "QML_IMPORT_PATH", "QML2_IMPORT_PATH",
                     "QT_ADDITIONAL_PACKAGES_PREFIX_PATH", "QT_ADDITIONAL_HOST_PACKAGES_PREFIX_PATH"):
        env.pop(variable, None)
    env["LC_ALL"] = "C"
    version = load_json(QT_PORT / "source_lock.json")["version"]
    for name, option in (("moc", "-v"), ("rcc", "-v"),
                         ("qmltyperegistrar", "--version"), ("qmlcachegen", "--version")):
        identity = subprocess.check_output([expected[name], option], env=env, text=True,
                                           stderr=subprocess.STDOUT)
        if f"{name} {version}" not in identity.splitlines():
            parser.error(f"Host {name} must report version {version}")
    output.mkdir(parents=True)
    binutils = output / "binutils"
    binutils.mkdir()
    for name in ("as", "ld"):
        (binutils / name).symlink_to(tools[name]["path"])
    font = output / "DejaVuSans.ttf"
    source_sha = extract_font(args.qtbase, font)

    packages = prefix / "lib/cmake"
    build = output / "build"
    includes = ";".join(profile["sdk_binding"]["cxx_runtime"]["include_directories"])
    configure = ["cmake", "-S", str(source), "-B", str(build), "-G", "Ninja",
                 "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF",
                 "-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF",
                 f"-DCMAKE_TOOLCHAIN_FILE={packages / 'Qt6/qt.toolchain.cmake'}",
                 f"-DQT_CHAINLOAD_TOOLCHAIN_FILE={QT_PORT / 'glibc/glibc_toolchain.cmake'}",
                 f"-DXOS_GLIBC_SDK={sdk_build / 'sysroot'}", f"-DXOS_GLIBC_TOOLS={binutils}",
                 f"-DXOS_GLIBC_CXX_INCLUDES={includes}", f"-DXOS_SOURCE_ROOT={ROOT}",
                 f"-DXOS_GLIBC_CC={tools['gcc']['path']}", f"-DXOS_GLIBC_CXX={tools['g++']['path']}",
                 f"-DXOS_GLIBC_AR={tools['ar']['path']}", f"-DXOS_GLIBC_RANLIB={tools['ranlib']['path']}",
                 f"-DQT_HOST_PATH={host_qt}", f"-DQT_ADDITIONAL_HOST_PACKAGES_PREFIX_PATH={host_qml}",
                 f"-DQt6QmlTools_DIR:PATH={host_qml / 'lib/cmake/Qt6QmlTools'}",
                 f"-DXOS_QUICK_QT_VERSION={version}",
                 f"-DXOS_QUICK_SUPPORT={PORT / 'XosQuickApp.cmake'}", f"-DXOS_QTBASE_FONT={font}"]
    configure.extend(f"-D{name}_DIR:PATH={packages / name}" for name in
                     ("Qt6", *(f"Qt6{module}" for module in MODULES), "Qt6QmlIntegration"))
    subprocess.run(configure, env=env, check=True)
    inputs_file = build / f"{args.target}-qt-inputs.txt"
    if not inputs_file.is_file():
        raise RuntimeError("The application must call xos_link_quick_app for the selected target")
    locations = dict(line.split("=", 1) for line in inputs_file.read_text().splitlines())
    selected = {name: Path(path).resolve(strict=True) for name, path in locations.items()}
    if selected != expected:
        raise RuntimeError("The application selected Qt archives or tools outside the bound kit")
    subprocess.run(["cmake", "--build", str(build), "--parallel", str(args.jobs),
                    "--target", args.target], env=env, check=True)
    if ({name: sha(path) for name, path in expected.items()} != input_digests
            or verify_profile(load_json(args.sdk_profile), "glibc", sdk_build) != binding
            or any(sha(Path(tool["path"])) != tool["sha256"] for tool in tools.values())
            or (kit_digest is not None and verify_kit(kit) != kit_digest)):
        raise RuntimeError("The SDK, Qt kit or toolchain changed during the application build")

    if target_digest is not None:
        observed_target = verify_target_receipt(
            args.target_receipt, tree_sha256=sdk_snapshot(prefix)[0], sdk_manifest=sdk_manifest,
            sdk_profile=sha(args.sdk_profile), inputs=input_digests)
        if observed_target != target_digest or sdk_snapshot(source)[0] != source_digest:
            raise RuntimeError("The Qt target build receipt or application source changed during the link")

    elf = Path((build / f"{args.target}-elf.txt").read_text().rstrip("\n")).resolve(strict=True)
    if not elf.is_relative_to(build) or not elf.is_file():
        raise RuntimeError("The application must link its ELF inside the build directory")
    receipt = {"status": "static_quick_application_linked", "guest_qualification": "not_run",
               "sdk_manifest_sha256": sdk_manifest, "qtbase_source_sha256": source_sha,
               "qt_inputs": input_digests,
               "target_tools": {name: tool["sha256"] for name, tool in tools.items()},
               "font_sha256": sha(font), "elf": elf.relative_to(output).as_posix(),
               "elf_sha256": sha(elf), "program_headers": verify_elf(elf)}
    if target_digest is not None:
        receipt["target_receipt_sha256"] = target_digest
        receipt["app_source_tree_sha256"] = source_digest
        receipt["sdk_profile_file_sha256"] = sha(args.sdk_profile)
    if kit_digest is not None:
        receipt["kit_manifest_sha256"] = kit_digest
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(elf)


if __name__ == "__main__":
    main()
