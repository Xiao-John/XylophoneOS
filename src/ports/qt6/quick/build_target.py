#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rebuild a static XOS Qt Quick or Widgets prefix for a verified glibc SDK."""

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from build_app import sha
from quick_kit import PORT, ROOT, QT_ROOT, WIDGETS_GENERATORS, kit_paths, qt_inputs, relocate_host_tools, verify_kit
from rebuild_declarative import allocator, patches, prepare_source, qml
from glibc_g1_probe import clean_build_environment, tool_identity
from xypm_format import canonical, load_json
from xypm_sdk_profile import metadata_snapshot, sdk_snapshot, verify_profile


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
WIDGETS_TOOLS_PACKAGE = Path("lib/cmake/Qt6WidgetsTools")
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


def stage_widgets_tools(host, destination):
    # A Quick kit can still have the original absolute Qt::uic export. Keep
    # the kit read-only and reuse all three binaries from the verified host Qt.
    with TemporaryDirectory(prefix=f".{destination.name}-", dir=destination.parent) as temporary:
        staged = Path(temporary) / destination.name
        package = staged / WIDGETS_TOOLS_PACKAGE
        package.parent.mkdir(parents=True)
        shutil.copytree(host / WIDGETS_TOOLS_PACKAGE, package)
        (staged / "libexec").symlink_to(host / "libexec", target_is_directory=True)
        relocate_host_tools(staged, (package.name,), generator_prefix=host)
        if destination.exists():
            if (not (destination / "libexec").is_symlink()
                    or (destination / "libexec").readlink() != host / "libexec"
                    or sdk_snapshot(destination / WIDGETS_TOOLS_PACKAGE)[0] != sdk_snapshot(package)[0]):
                raise ValueError("Previous Widgets tools export differs from the verified host package")
        else:
            staged.rename(destination)
    return destination / WIDGETS_TOOLS_PACKAGE


def inputs_for(args, sdk, paths):
    widgets = args.component == "widgets"
    profile, profile_digest = metadata_snapshot(args.sdk_profile)
    binding = verify_profile(profile, "glibc", sdk)
    if not {"cxx_runtime", "threads"} <= set(profile["features"]):
        raise ValueError("The Qt target needs a glibc profile with C++ and threads")
    manifest, sdk_digest = metadata_snapshot(sdk / "manifest.json", profile["sdk_binding"]["sdk_manifest_sha256"])
    tools = {name: tool_identity(f"x86_64-elf-{name}") for name in CROSS_TOOLS}
    for name, identity in tools.items():
        if identity.get("sha256") != manifest["tools"][f"x86_64-elf-{name}"]["sha256"]:
            raise ValueError(f"Cross tool differs from the SDK build: {name}")
    archives = {"qtbase": sha(paths["qtbase"])}
    recipes = [Path(__file__), *BASE_PATCHES, QT_ROOT / "source_lock.json",
               QT_ROOT / "glibc/glibc_toolchain.cmake"]
    if widgets:
        native_tools = {name: sha(paths["host_qt"] / "libexec" / name) for name in WIDGETS_GENERATORS}
        widgets_config = paths["host_qt"] / WIDGETS_TOOLS_PACKAGE
        if not (widgets_config / "Qt6WidgetsToolsConfig.cmake").is_file():
            raise ValueError("Host Qt is missing the Widgets tools CMake package")
        recipes.append(PORT / "quick_kit.py")
    else:
        archives["qtdeclarative"] = sha(args.declarative)
        if archives["qtdeclarative"] != load_json(qml / "source_lock.json")["sha256"]:
            raise ValueError("Qt Declarative archive differs from its source lock")
        native_inputs = qt_inputs(paths["target_prefix"], paths["host_qt"], paths["host_qml"])
        native_tools = {name: sha(path) for name, path in native_inputs.items()
                        if path.is_relative_to(paths["host_qt"]) or path.is_relative_to(paths["host_qml"])}
        native_tools["qsb"] = sha(paths["host_qt"] / "bin/qsb")
        recipes.extend([allocator, *patches, qml / "source_lock.json", PORT / "source_lock.json"])
    recipes.extend(QT_ROOT / filename for filename in ("prepare_source.py", "prepare_gui_source.py"))
    recipes.extend(path for directory in ("patches", "runtime", "cmake", "mkspecs")
                   for path in (QT_ROOT / directory).rglob("*") if path.is_file())
    recipe_hashes = {path.relative_to(ROOT).as_posix(): sha(path) for path in sorted(set(recipes))}
    receipt = {"sdk_binding": binding, "sdk_manifest_sha256": sdk_digest,
               "sdk_profile_file_sha256": profile_digest, "host_kit_manifest_sha256": verify_kit(args.host_kit),
               "sources": archives, "native_generators": native_tools, "recipes": recipe_hashes,
               "cross_tools": {name: identity["sha256"] for name, identity in tools.items()}}
    if widgets:
        receipt["qt_version"] = load_json(QT_ROOT / "source_lock.json")["version"]
        receipt["qtbase_features"] = {"widgets": "ON", "filedialog": "OFF"}
    return receipt, tools, profile


def rebuild(args):
    args.host_kit = args.host_kit.resolve(strict=True)
    if args.declarative is not None:
        args.declarative = args.declarative.resolve(strict=True)
    args.sdk_profile = args.sdk_profile.resolve(strict=True)
    sdk = args.sdk_build.resolve(strict=True)
    output = args.output.resolve()
    widgets = args.component == "widgets"
    if any(output.is_relative_to(path) for path in (sdk, args.host_kit, ROOT / "src", ROOT / "tests")):
        raise ValueError("The output must be outside all input trees")
    paths = kit_paths(args.host_kit)
    receipt, tools, profile = inputs_for(args, sdk, paths)
    env = build_environment()

    def run(command, cwd=None):
        subprocess.run(command, check=True, cwd=cwd, env=env)

    version = load_json(QT_ROOT / "source_lock.json")["version"]
    host = paths["host_qt"]
    generators = [(host / "libexec" / name, "-v") for name in WIDGETS_GENERATORS] if widgets else [
        (host / "bin/qsb", "--version")]
    for generator, option in generators:
        reported = subprocess.check_output([generator, option], text=True, env=env, stderr=subprocess.STDOUT)
        if f"{generator.name} {version}" not in reported.splitlines():
            raise ValueError(f"Host {generator.name} does not match the Qt source version")
    if args.check_inputs:
        print(canonical(receipt | {"status": "qt_target_inputs_verified", "component": args.component}).decode(),
              end="")
        return
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
    features = {name: "OFF" for name in BASE_FEATURES_OFF}
    if widgets:
        features.update(receipt["qtbase_features"])
        widgets_tools = stage_widgets_tools(host, output / "host_widgets_tools")
        common.append(f"-DQt6WidgetsTools_DIR:PATH={widgets_tools}")
    run(["cmake", "-S", source, "-B", base, *common, f"-DCMAKE_TOOLCHAIN_FILE={chainload}",
         "-DQT_QMAKE_TARGET_MKSPEC=xos-g++", "-DFEATURE_gui=ON", "-DFEATURE_freetype=ON",
         "-DFEATURE_harfbuzz=ON", "-DINPUT_freetype=qt", "-DINPUT_harfbuzz=qt",
         "-DINPUT_opengl=no", "-DQT_QPA_DEFAULT_PLATFORM=xos",
         *[f"-DFEATURE_{name}={value}" for name, value in features.items()]])
    run(["cmake", "--build", base, "--parallel", jobs])
    run(["cmake", "--install", base])
    (output / "qtbase_installed.json").write_bytes(canonical({
        name: sha(prefix / "lib" / f"libQt6{name}.a")
        for name in (("Core", "Gui", "Widgets") if widgets else ("Core", "Gui"))
    }))
    if widgets:
        cache = base / "CMakeCache.txt"
        cache_lines = set(cache.read_text().splitlines())
        for name, value in receipt["qtbase_features"].items():
            if f"QT_FEATURE_{name}:INTERNAL={value}" not in cache_lines:
                raise ValueError(f"QtBase configured the wrong effective {name} feature")
        if inputs_for(args, sdk, paths)[0] != receipt:
            raise ValueError("A build input changed during the Qt Widgets build")
        receipt["qtbase_prepared_tree_sha256"] = sdk_snapshot(source)[0]
        receipt["qt_build_cache_sha256"] = sha(cache)
        receipt["target_tree_sha256"] = sdk_snapshot(prefix)[0]
        receipt["status"] = "static_qt_widgets_target_installed"
        (output / "target_receipt.json").write_bytes(canonical(receipt))
        return

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
    if inputs_for(args, sdk, paths)[0] != receipt:
        raise ValueError("A build input changed during the Qt Quick build")
    installed = qt_inputs(prefix, paths["host_qt"], host_qml)
    receipt["target_tree_sha256"] = sdk_snapshot(prefix)[0]
    receipt["target_inputs"] = {name: sha(path) for name, path in installed.items() if path.is_relative_to(prefix)}
    receipt["status"] = "static_qt_quick_target_installed"
    (output / "target_receipt.json").write_bytes(canonical(receipt))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("host-kit", "sdk-build", "sdk-profile", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--component", choices=("quick", "widgets"), default="quick")
    parser.add_argument("--declarative", type=Path, help="locked Qt Declarative archive for the Quick target")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--check-inputs", action="store_true", help="validate inputs without configuring or building")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    if (args.declarative is not None) != (args.component == "quick"):
        parser.error("--declarative is required for Quick and unused for Widgets")
    if args.check_inputs and args.resume:
        parser.error("--check-inputs cannot be combined with --resume")
    rebuild(args)


if __name__ == "__main__":
    main()
