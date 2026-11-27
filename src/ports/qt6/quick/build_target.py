#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rebuild the static XOS Qt Quick target prefix for a verified glibc SDK."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from build_app import sha
from quick_kit import PORT, ROOT, QT_ROOT, kit_paths, qt_inputs, verify_kit
from rebuild_declarative import allocator, patches, prepare_source, qml
from glibc_g1_probe import clean_build_environment, tool_identity
from xypm_format import canonical, load_json
from xypm_sdk_profile import sdk_snapshot, verify_profile


BASE_FEATURES_OFF = """
testlib concurrent xml network sql dbus icu glib stack_protector intelcet
stack_clash_protection poll_select poll_poll poll_ppoll poll_pollts process
processenvironment filesystemwatcher sharedmemory systemsemaphore futimens memmem
memrchr library dlopen widgets opengl egl eglfs xcb xcb_xlib vulkan fontconfig
system_freetype system_harfbuzz png jpeg gif pdf sessionmanager cups evdev libinput
tslib linuxfb vnc directfb integrityfb vkkhrdisplay system_zlib system_pcre2
""".split()
DECLARATIVE_FEATURES_OFF = """
qml_jit qml_debug qml_worker_script quick_shadereffect quick_particles quick_designer
""".split()
CROSS_TOOLS = ("gcc", "g++", "as", "ld", "ar", "ranlib")
BASE_PATCHES = (QT_ROOT / "glibc/glibc_qtcore.patch", PORT / "glibc_qtbase_platform.patch")


def build_environment():
    env, _ = clean_build_environment(os.environ)
    for name in ("CMAKE_PREFIX_PATH", "Qt6_DIR", "Qt6_ROOT", "QML_IMPORT_PATH", "QML2_IMPORT_PATH",
                 "QT_ADDITIONAL_PACKAGES_PREFIX_PATH", "QT_ADDITIONAL_HOST_PACKAGES_PREFIX_PATH"):
        env.pop(name, None)
    env["LC_ALL"] = "C.UTF-8"
    return env


@contextmanager
def stage_source(destination):
    # The final path is the completion marker used by --resume. Keep the
    # temporary tree on the same filesystem so publishing it is atomic.
    with TemporaryDirectory(prefix=f".{destination.name}-", dir=destination.parent) as temporary:
        staged = Path(temporary) / destination.name
        yield staged
        staged.rename(destination)


def copy_declarative_packages(build, prefix, run):
    for module in ("qmlintegration", "qml", "qmlmodels", "qmlmeta", "quick"):
        run(["cmake", "--install", build / "src" / module, "--prefix", prefix])
    packages = build / "lib/cmake"
    installed = prefix / "lib/cmake"
    for module in ("Qml", "QmlMeta", "QmlModels", "Quick"):
        path = Path(f"Qt6{module}/Qt6{module}Dependencies.cmake")
        shutil.copyfile(packages / path, installed / path)
    for plugin in ("modelsplugin", "qmlplugin", "qtquick2plugin"):
        path = Path(f"Qt6Qml/QmlPlugins/Qt6{plugin}Dependencies.cmake")
        shutil.copyfile(packages / path, installed / path)
    for module in ("Qml", "Quick"):
        path = Path(f"Qt6{module}/Qt6{module}Plugins.cmake")
        shutil.copyfile(packages / path, installed / path)


def inputs_for(args, sdk, profile, paths):
    binding = verify_profile(profile, "glibc", sdk)
    manifest = load_json(sdk / "manifest.json")
    tools = {name: tool_identity(f"x86_64-elf-{name}") for name in CROSS_TOOLS}
    for name, identity in tools.items():
        if identity.get("sha256") != manifest["tools"][f"x86_64-elf-{name}"]["sha256"]:
            raise ValueError(f"Cross tool differs from the SDK build: {name}")
    archives = {name: sha(path) for name, path in
                (("qtbase", paths["qtbase"]), ("qtdeclarative", args.declarative))}
    if archives["qtdeclarative"] != load_json(qml / "source_lock.json")["sha256"]:
        raise ValueError("Qt Declarative archive differs from its source lock")
    native_tools = {
        name: sha(path) for name, path in
        qt_inputs(paths["target_prefix"], paths["host_qt"], paths["host_qml"]).items()
        if path.is_relative_to(paths["host_qt"]) or path.is_relative_to(paths["host_qml"])
    }
    qsb = paths["host_qt"] / "bin/qsb"
    native_tools["qsb"] = sha(qsb)
    recipes = [Path(__file__), allocator, *BASE_PATCHES, *patches, QT_ROOT / "source_lock.json",
               qml / "source_lock.json", PORT / "source_lock.json", QT_ROOT / "glibc/glibc_toolchain.cmake"]
    recipes.extend(QT_ROOT / filename for filename in ("prepare_source.py", "prepare_gui_source.py"))
    recipes.extend(path for directory in ("patches", "runtime", "cmake", "mkspecs")
                   for path in (QT_ROOT / directory).rglob("*") if path.is_file())
    recipe_hashes = {path.relative_to(ROOT).as_posix(): sha(path) for path in sorted(set(recipes))}
    receipt = {"sdk_binding": binding, "sdk_manifest_sha256": sha(sdk / "manifest.json"),
               "sdk_profile_file_sha256": sha(args.sdk_profile), "host_kit_manifest_sha256": verify_kit(args.host_kit),
               "sources": archives, "native_generators": native_tools, "recipes": recipe_hashes,
               "cross_tools": {name: identity["sha256"] for name, identity in tools.items()}}
    return receipt, tools


def rebuild(args):
    args.host_kit = args.host_kit.resolve(strict=True)
    args.declarative = args.declarative.resolve(strict=True)
    args.sdk_profile = args.sdk_profile.resolve(strict=True)
    sdk = args.sdk_build.resolve(strict=True)
    output = args.output.resolve()
    if any(output.is_relative_to(path) for path in (sdk, args.host_kit, ROOT / "src", ROOT / "tests")):
        raise ValueError("The output must be outside all input trees")
    paths = kit_paths(args.host_kit)
    profile = load_json(args.sdk_profile)
    receipt, tools = inputs_for(args, sdk, profile, paths)
    env = build_environment()

    def run(command, cwd=None):
        subprocess.run(command, check=True, cwd=cwd, env=env)

    version = load_json(QT_ROOT / "source_lock.json")["version"]
    qsb = paths["host_qt"] / "bin/qsb"
    if f"qsb {version}" not in subprocess.check_output([qsb, "--version"], text=True, env=env).splitlines():
        raise ValueError("Host qsb does not match the Qt source version")
    input_file = output / "inputs.json"
    if args.resume:
        if load_json(input_file) != receipt:
            raise ValueError("Build inputs changed since the initial recipe")
    else:
        output.mkdir(parents=True)
        input_file.write_bytes(canonical(receipt))
    binutils = output / "binutils"
    binutils.mkdir(exist_ok=True)
    for name in ("as", "ld"):
        link = binutils / name
        selected = Path(tools[name]["path"])
        if not link.is_symlink():
            link.symlink_to(selected)
        if link.resolve(strict=True) != selected.resolve(strict=True):
            raise ValueError(f"Previous binutils binding differs: {name}")

    source = output / "qtbase_source"
    base = output / "qtbase_build"
    prefix = output / "target"
    includes = ";".join(profile["sdk_binding"]["cxx_runtime"]["include_directories"])
    chainload = QT_ROOT / "glibc/glibc_toolchain.cmake"
    common = ["-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
              "-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF", "-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF",
              "-DCMAKE_DISABLE_PRECOMPILE_HEADERS=ON", "-DBUILD_SHARED_LIBS=OFF",
              "-DQT_BUILD_EXAMPLES=OFF", "-DQT_BUILD_TESTS=OFF", "-DQT_BUILD_BENCHMARKS=OFF",
              f"-DCMAKE_INSTALL_PREFIX={prefix}", f"-DQT_HOST_PATH={paths['host_qt']}",
              f"-DXOS_GLIBC_SDK={sdk / 'sysroot'}", f"-DXOS_GLIBC_TOOLS={binutils}",
              f"-DXOS_GLIBC_CXX_INCLUDES={includes}", f"-DXOS_SOURCE_ROOT={ROOT}"]
    common.extend(f"-DXOS_GLIBC_{label}={tools[name]['path']}" for label, name in
                  (("CC", "gcc"), ("CXX", "g++"), ("AR", "ar"), ("RANLIB", "ranlib")))
    if not source.exists():
        with stage_source(source) as staged:
            run([sys.executable, QT_ROOT / "prepare_gui_source.py", paths["qtbase"], staged])
            for patch in BASE_PATCHES:
                run(["patch", "--batch", "--fuzz=0", "-p1", "-i", patch], cwd=staged)
    jobs = str(args.jobs)
    run(["cmake", "-S", source, "-B", base, *common, f"-DCMAKE_TOOLCHAIN_FILE={chainload}",
         "-DQT_QMAKE_TARGET_MKSPEC=xos-g++", "-DFEATURE_gui=ON", "-DFEATURE_freetype=ON",
         "-DFEATURE_harfbuzz=ON", "-DINPUT_freetype=qt", "-DINPUT_harfbuzz=qt",
         "-DINPUT_opengl=no", "-DQT_QPA_DEFAULT_PLATFORM=xos",
         *[f"-DFEATURE_{name}=OFF" for name in BASE_FEATURES_OFF]])
    run(["cmake", "--build", base, "--parallel", jobs])
    run(["cmake", "--install", base])
    (output / "qtbase_installed.json").write_bytes(canonical({
        name: sha(prefix / "lib" / f"libQt6{name}.a") for name in ("Core", "Gui")
    }))

    declarative = output / "qtdeclarative_source"
    if not declarative.exists():
        with stage_source(declarative) as staged:
            prepare_source(args.declarative, staged, version, env)
    declarative_source = declarative / f"qtdeclarative-everywhere-src-{version}"
    build = output / "qtdeclarative_build"
    packages = prefix / "lib/cmake"
    host_qml = paths["host_qml"]
    run(["cmake", "-S", declarative_source, "-B", build, *common,
         f"-DCMAKE_TOOLCHAIN_FILE={packages / 'Qt6/qt.toolchain.cmake'}",
         f"-DQT_CHAINLOAD_TOOLCHAIN_FILE={chainload}", f"-DQt6_DIR:PATH={packages / 'Qt6'}",
         f"-DQT_ADDITIONAL_HOST_PACKAGES_PREFIX_PATH={host_qml}",
         f"-DQt6QmlTools_DIR:PATH={host_qml / 'lib/cmake/Qt6QmlTools'}",
         f"-DQt6ShaderToolsTools_DIR:PATH={paths['host_qt'] / 'lib/cmake/Qt6ShaderToolsTools'}",
         "-DQT_GENERATE_SBOM=OFF", *[f"-DFEATURE_{name}=OFF" for name in DECLARATIVE_FEATURES_OFF]])
    run(["cmake", "--build", build, "--parallel", jobs, "--target", "Quick",
         "qtquick2plugin", "qtquick2plugin_init", "qmlplugin", "qmlplugin_init", "modelsplugin",
         "modelsplugin_init", "quickwindow", "quickwindow_init", "quickwindow_resources_1"])
    copy_declarative_packages(build, prefix, run)
    if inputs_for(args, sdk, load_json(args.sdk_profile), paths)[0] != receipt:
        raise ValueError("A build input changed during the Qt Quick build")
    installed = qt_inputs(prefix, paths["host_qt"], host_qml)
    receipt["target_tree_sha256"] = sdk_snapshot(prefix)[0]
    receipt["target_inputs"] = {name: sha(path) for name, path in installed.items() if path.is_relative_to(prefix)}
    receipt["status"] = "static_qt_quick_target_installed"
    (output / "target_receipt.json").write_bytes(canonical(receipt))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("host-kit", "sdk-build", "sdk-profile", "declarative", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    rebuild(args)


if __name__ == "__main__":
    main()
