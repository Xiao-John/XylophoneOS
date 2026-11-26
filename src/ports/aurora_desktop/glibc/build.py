#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the existing Mobius desktop and session with one verified glibc Widgets build."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

PORT = Path(__file__).resolve().parent
ROOT = PORT.parents[3]
QT = ROOT / "src/ports/qt6"
sys.path.insert(0, str(ROOT / "scripts"))

from build_glibc_program import sha, verify_elf
from glibc_g1_probe import clean_build_environment, tool_identity
from xypm_format import load_json
from xypm_sdk_profile import metadata_snapshot, verify_profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("sdk-build", "sdk-profile", "qt-build", "qt-prefix", "qt-source", "host-qt", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    sdk_build, qt_build, prefix, qt_source, host = (
        path.resolve(strict=True) for path in
        (args.sdk_build, args.qt_build, args.qt_prefix, args.qt_source, args.host_qt))
    sdk = sdk_build / "sysroot"
    output = args.output.resolve()
    if args.jobs < 1 or args.sdk_build.is_symlink() or args.output.is_symlink() or output.exists():
        parser.error("Use a real SDK directory, a fresh output path and a positive job count")
    if any(output.is_relative_to(path) for path in (sdk_build, qt_build, prefix, qt_source, host, PORT)):
        parser.error("Put the build output outside the input trees")

    profile = load_json(args.sdk_profile)
    binding = verify_profile(profile, "glibc", sdk_build)
    if (not {"cxx_runtime", "threads"} <= set(profile["features"])
            or "usr/lib/libxos_terminal.a" not in profile["sdk_binding"]["link_artifacts"]):
        parser.error("The glibc profile must bind C++, threads and the XOS terminal runtime")
    sdk_manifest = sdk_build / "manifest.json"
    manifest, _ = metadata_snapshot(sdk_manifest, profile["sdk_binding"]["sdk_manifest_sha256"])
    tools = {name: tool_identity(f"x86_64-elf-{name}")
             for name in ("gcc", "g++", "as", "ld", "ar", "ranlib")}
    for name, tool in tools.items():
        if tool.get("sha256") != manifest["tools"][f"x86_64-elf-{name}"]["sha256"]:
            parser.error(f"x86_64-elf-{name} differs from the SDK build")

    cache_path = qt_build / "CMakeCache.txt"
    cache = dict(line.split("=", 1) for line in cache_path.read_text().splitlines()
                 if line and not line.startswith(("#", "//")) and "=" in line)
    if (cache.get("FEATURE_widgets:BOOL") != "ON"
            or cache.get("CMAKE_HOME_DIRECTORY:INTERNAL") != str(qt_source)
            or cache.get("XOS_GLIBC_SDK:UNINITIALIZED") != str(sdk)
            or cache.get("CMAKE_INSTALL_PREFIX:PATH") != str(prefix)):
        parser.error("Qt Widgets configuration must match the source, installed prefix and glibc sysroot")

    modules = ("Core", "Gui", "Widgets", "BundledFreetype", "BundledHarfbuzz", "BundledPcre2", "BundledZLIB")
    archives = {module: prefix / "lib" / f"libQt6{module}.a" for module in modules}
    installed_tools = {name: host / "libexec" / name for name in ("moc", "rcc")}
    qt_inputs = archives | installed_tools
    expected = {name: path.resolve(strict=True) for name, path in qt_inputs.items()}
    for path in archives.values():
        if sha(path) != sha(qt_build / "lib" / path.name):
            parser.error(f"Installed archive differs from the matching Qt Widgets build: {path.name}")
    env, _ = clean_build_environment(os.environ)
    for name in ("CMAKE_PREFIX_PATH", "Qt6_DIR", "Qt6_ROOT", "QT_ADDITIONAL_PACKAGES_PREFIX_PATH",
                 "QT_ADDITIONAL_HOST_PACKAGES_PREFIX_PATH"):
        env.pop(name, None)
    env["LC_ALL"] = "C"
    version = load_json(QT / "source_lock.json")["version"]
    for name, path in installed_tools.items():
        tool_version = subprocess.check_output([path, "-v"], text=True, stderr=subprocess.STDOUT, env=env)
        if f"{name} {version}" not in tool_version.splitlines():
            parser.error(f"Host {name} must report version {version}")

    output.mkdir(parents=True)
    binutils = output / "binutils"
    binutils.mkdir()
    for name in ("as", "ld"):
        (binutils / name).symlink_to(tools[name]["path"])
    packages = prefix / "lib/cmake"
    includes = ";".join(profile["sdk_binding"]["cxx_runtime"]["include_directories"])
    qt_port_inputs = [QT / "glibc/glibc_toolchain.cmake", QT / "glibc/xos_qpa.cmake", QT / "cmake/Platform/XOS.cmake",
                      QT / "qpa/qxos.cpp", QT / "qpa/xos.json", QT / "source_lock.json",
                      *sorted((QT / "runtime").glob("*.[ch]*")),
                      *sorted((QT / "aurora").glob("*.[ch]*")),
                      *(QT / "aurora/assets" / name for name in ("aurora.bmp", "curvive_wallpaper.bmp"))]
    product_inputs = [PORT / "CMakeLists.txt", Path(__file__).resolve(),
                      PORT.parent / "main.cpp", PORT.parent / "session.cpp"]
    xos_headers = [path for directory in (ROOT / "src/shared/include", ROOT / "src/user/include")
                   for path in sorted(directory.rglob("*")) if path.suffix in (".h", ".hpp")]
    font = qt_source / "src/3rdparty/wasm/DejaVuSans.ttf"
    paths = [sdk_manifest, args.sdk_profile.resolve(), cache_path, font,
             *product_inputs, *qt_port_inputs, *xos_headers, *qt_inputs.values()]
    digests = {str(path): sha(path) for path in paths}
    configure = ["cmake", "-S", str(PORT), "-B", str(output), "-G", "Ninja",
                 "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF",
                 "-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF",
                 f"-DCMAKE_TOOLCHAIN_FILE={packages / 'Qt6/qt.toolchain.cmake'}",
                 f"-DQT_CHAINLOAD_TOOLCHAIN_FILE={QT / 'glibc/glibc_toolchain.cmake'}",
                 f"-DXOS_QT_PREFIX={prefix}", f"-DXOS_QTBASE_SOURCE={qt_source}", f"-DQT_HOST_PATH={host}",
                 f"-DXOS_GLIBC_SDK={sdk}", f"-DXOS_GLIBC_TOOLS={binutils}",
                 f"-DXOS_SOURCE_ROOT={ROOT}", f"-DXOS_GLIBC_CXX_INCLUDES={includes}",
                 f"-DXOS_GLIBC_CC={tools['gcc']['path']}", f"-DXOS_GLIBC_CXX={tools['g++']['path']}",
                 f"-DXOS_GLIBC_AR={tools['ar']['path']}", f"-DXOS_GLIBC_RANLIB={tools['ranlib']['path']}"]
    configure.extend(f"-D{name}_DIR:PATH={packages / name}"
                     for name in ("Qt6", *(f"Qt6{module}" for module in modules)))
    subprocess.run(configure, env=env, check=True)
    lines = (output / "qt_inputs.txt").read_text().splitlines()
    selected = {name: Path(path).resolve(strict=True) for name, path in (line.split("=", 1) for line in lines)}
    if selected != expected:
        raise RuntimeError("Mobius selected Qt libraries or generators outside the matched Widgets kit")
    loader_sources = [Path(path) for path in (output / "loader_sources.txt").read_text().split(";")]
    paths.extend(loader_sources)
    digests.update({str(path): sha(path) for path in loader_sources})
    build = ["cmake", "--build", str(output), "--parallel", str(args.jobs)]
    subprocess.run(build, env=env, check=True)
    if ({str(path): sha(path) for path in paths} != digests
            or any(path.resolve(strict=True) != expected[name] for name, path in qt_inputs.items())
            or verify_profile(load_json(args.sdk_profile), "glibc", sdk_build) != binding
            or any(sha(Path(tool["path"])) != tool["sha256"] for tool in tools.values())):
        raise RuntimeError("Mobius build inputs changed during compilation")

    for name in ("mobius", "mobius_session"):
        elf = output / f"{name}.elf"
        receipt = {"elf_sha256": sha(elf), "program_headers": verify_elf(elf),
                   "commands": [configure, build], "inputs": digests,
                   "sdk_manifest_sha256": sha(sdk_manifest), "sdk_tree_sha256": binding["sdk_tree_sha256"],
                   "target_tools": {name: tool["sha256"] for name, tool in tools.items()},
                   "guest_qualification": "not_run"}
        elf.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print(elf)


if __name__ == "__main__":
    main()
