# SPDX-License-Identifier: Apache-2.0
"""Build native LLInt layout headers and focused WTF or JSC target objects for XOS."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
import sys

port = Path(__file__).resolve().parent
root = port.parents[2]
sys.path.insert(0, str(root / "scripts"))
from build_glibc_program import verify_elf
from glibc_g1_probe import clean_build_environment, tool_identity
from xypm_format import load_json
from xypm_sdk_profile import metadata_snapshot, verify_profile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def match(path, expected):
    if digest(path) != expected:
        raise ValueError("input digest mismatch: " + path.name)


def build(args):
    lock_path = port / "source_lock.json"
    recipe_digest = digest(Path(__file__))
    lock_digest = digest(lock_path)
    lock = json.loads(lock_path.read_bytes())
    match(args.archive, lock["sha256"])
    if args.archive.stat().st_size != lock["bytes"]:
        raise ValueError("WebKit archive size mismatch")
    for name, checksum in lock["patches"].items():
        match(port / name, checksum)
    icu_lock = lock["llint_icu"]
    match(args.icu_archive, icu_lock["archive_sha256"])

    profile = load_json(args.sdk_profile)
    binding = verify_profile(profile, "glibc", args.sdk_build)
    if "cxx_runtime" not in profile["features"] or binding["sdk_tree_sha256"] != icu_lock["sdk_tree_sha256"]:
        raise ValueError("the ICU input must match the bound glibc C/C++ SDK")
    manifest, manifest_digest = metadata_snapshot(args.sdk_build / "manifest.json",
                                                  profile["sdk_binding"]["sdk_manifest_sha256"])
    tools = {}
    for suffix in ("gcc", "g++", "as", "ld", "ar", "ranlib"):
        name = "x86_64-elf-" + suffix
        info = tool_identity(name)
        if info.get("sha256") != manifest["tools"][name]["sha256"]:
            raise ValueError(name + " differs from the glibc SDK build")
        tools[suffix] = info

    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    env, _ = clean_build_environment(os.environ)
    env["LC_ALL"] = "C"

    def run(stage, command, *, cwd=None):
        report = output / (stage + ".log")
        with report.open("w") as stream:
            result = subprocess.run(command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode != 0:
            raise RuntimeError(stage + " failed; see " + str(report))

    archive_root = lock["archive_root"]
    source_parent, icu, drivers = (output / name for name in ("source", "icu", "drivers"))
    for directory in (source_parent, icu, drivers):
        directory.mkdir()
    native_headers = {name: digest(root / name) for name in (
        "src/shared/include/xos/abi_types.hpp", "src/shared/include/xos/file_abi.hpp",
        "src/shared/include/xos/process_abi.hpp", "src/shared/include/xos/thread_abi.hpp",
        "src/user/include/xos/sdk.hpp", "src/user/include/xos/spawn.hpp")}
    native_include = drivers / "native"
    (native_include / "xos").mkdir(parents=True)
    for name, checksum in native_headers.items():
        destination = native_include / "xos" / Path(name).name
        shutil.copyfile(root / name, destination)
        match(destination, checksum)
    members = ("CMakeLists.txt", "Source/CMakeLists.txt", "Source/cmake", "Source/JavaScriptCore",
               "Source/WTF", "Source/bmalloc", "Source/ThirdParty/gtest", "Source/ThirdParty/unifdef", "Tools")
    run("unpack_webkit", ["tar", "-xJf", args.archive, "-C", source_parent,
                          *(archive_root + "/" + member for member in members)])
    source = source_parent / archive_root
    for name in sorted(lock["patches"]):
        run(Path(name).stem, ["patch", "-d", source, "-p1", "-i", port / name])
    platform_sources = source / "Source/WTF/wtf/xos"
    platform_sources.mkdir()
    for name, checksum in lock["platform_sources"].items():
        destination = platform_sources / Path(name).name
        shutil.copyfile(port / name, destination)
        match(destination, checksum)
    run("unpack_icu", ["tar", "--zstd", "-xf", args.icu_archive, "-C", icu])
    for name, checksum in icu_lock["artifacts"].items():
        match(icu / name, checksum)

    unifdef = drivers / "unifdef"
    run("host_unifdef", ["cc", "-std=gnu99", "-O2", source / "Source/ThirdParty/unifdef/unifdef.c",
                        "-o", unifdef])

    for driver in ("cc", "cxx"):
        (drivers / driver).symlink_to(port / "icu/xos-compiler")
    includes = drivers / "cxx-includes.txt"
    includes.write_text("\n".join(profile["sdk_binding"]["cxx_runtime"]["include_directories"]) + "\n")
    sdk = args.sdk_build.absolute() / "sysroot"
    env.update(XOS_ICU_SDK=str(sdk), XOS_ICU_CXX_INCLUDES=str(includes),
               XOS_ICU_CC=tools["gcc"]["path"], XOS_ICU_CXX=tools["g++"]["path"])
    tool_dir = drivers / "binutils"
    tool_dir.mkdir()
    for suffix in ("as", "ld"):
        (tool_dir / suffix).symlink_to(tools[suffix]["path"])
    env["COMPILER_PATH"] = str(tool_dir)

    layout = output / "layout"
    extra_config = []
    if args.stage == "jsc_mutator":
        extra_config.extend(["-DENABLE_UNIFIED_BUILDS=OFF", "-DCMAKE_DISABLE_PRECOMPILE_HEADERS=ON",
                             "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"])
    run("configure", ["cmake", "-S", source, "-B", layout, "-G", "Ninja",
                       "-DPORT=JSCOnly", "-DENABLE_STATIC_JSC=ON", "-DUSE_SYSTEM_MALLOC=ON",
                       "-DENABLE_JIT=OFF", "-DENABLE_C_LOOP=OFF", "-DENABLE_WEBASSEMBLY=OFF",
                       "-DENABLE_SAMPLING_PROFILER=OFF",
                       "-DUSE_SYSTEM_UNIFDEF=ON", f"-DUNIFDEF_EXECUTABLE={unifdef}",
                       "-DUSE_LIBBACKTRACE=OFF", "-DCMAKE_BUILD_TYPE=Release",
                       "-DCMAKE_SYSTEM_NAME=XOS", "-DCMAKE_SYSTEM_PROCESSOR=x86_64",
                       f"-DXOS_NATIVE_ABI_INCLUDE={native_include}",
                       "-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY", f"-DCMAKE_SYSROOT={sdk}",
                       f"-DCMAKE_FIND_ROOT_PATH={sdk};{icu}", "-DCMAKE_FIND_ROOT_PATH_MODE_PROGRAM=NEVER",
                       "-DCMAKE_FIND_ROOT_PATH_MODE_LIBRARY=ONLY", "-DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=ONLY",
                       "-DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=ONLY",
                       f"-DCMAKE_C_COMPILER={drivers / 'cc'}", f"-DCMAKE_CXX_COMPILER={drivers / 'cxx'}",
                       f"-DCMAKE_AR={tools['ar']['path']}", f"-DCMAKE_RANLIB={tools['ranlib']['path']}",
                       f"-DICU_INCLUDE_DIR={icu / 'include'}",
                       f"-DICU_DATA_LIBRARY_RELEASE={icu / 'lib/libicudata.a'}",
                       f"-DICU_UC_LIBRARY_RELEASE={icu / 'lib/libicuuc.a'}",
                       f"-DICU_I18N_LIBRARY_RELEASE={icu / 'lib/libicui18n.a'}", *extra_config])
    if args.stage == "layout":
        derived = "JavaScriptCore/DerivedSources/"
        target = derived + "LLIntAssembly.h"
        run("layout", ["cmake", "--build", layout, "--target", target, "--parallel", "1"])
        extractors = ("bin/LLIntSettingsExtractor", "bin/LLIntOffsetsExtractor")
        for name in extractors:
            verify_elf(layout / name)
        artifacts = (*extractors, derived + "LLIntDesiredSettings.h", derived + "LLIntDesiredOffsets.h", target)
        if any((layout / name).stat().st_size == 0 for name in artifacts):
            raise RuntimeError("layout generator produced an empty artifact")
        assembly = (layout / target).read_text()
        if "OFFLINE_ASM_GLOBAL_LABEL(vmEntryToJavaScript)" not in assembly or '"push %rbp ' not in assembly:
            raise RuntimeError("layout generator did not emit the native x86-64 interpreter entry")
        status = "target_llint_assembly_generated"
    else:
        if args.stage in ("wtf_stack", "wtf_pthread"):
            object_dir = "Source/WTF/wtf/CMakeFiles/WTF.dir/"
            names = ("StackBounds.cpp.obj", "xos/xos_stack_bounds.cpp.obj", "Threading.cpp.obj")
            if args.stage == "wtf_pthread":
                names += ("posix/ThreadingPOSIX.cpp.obj",)
            artifacts = tuple(object_dir + name for name in names)
            status = "target_" + args.stage + "_objects_compiled"
            run(args.stage, ["cmake", "--build", layout, "--target", *artifacts, "--parallel", "1"])
        else:
            artifacts = ("Source/JavaScriptCore/CMakeFiles/JavaScriptCore.dir/runtime/JSLock.cpp.obj",)
            status = "target_jsc_mutator_admission_object_compiled"
            # Building this Ninja object target also builds its ordered library
            # dependencies. Compile the same unit after generating its headers.
            run("jsc_mutator_headers", ["cmake", "--build", layout, "--target",
                                       "JavaScriptCore_CopyPrivateHeaders", "JavaScriptCore_CopyHeaders",
                                       "WTF_CopyHeaders", "bmalloc_CopyHeaders", "--parallel", "1"])
            commands = json.loads((layout / "compile_commands.json").read_bytes())
            unit, = (item for item in commands if layout / item.get("output", "") == layout / artifacts[0]
                     and item["file"] == str(source / "Source/JavaScriptCore/runtime/JSLock.cpp")
                     and item["directory"] == str(layout))
            run(args.stage, shlex.split(unit["command"]), cwd=layout)
        for name in artifacts:
            with (layout / name).open("rb") as stream:
                header = stream.read(64)
            if (len(header) != 64 or header[:7] != b"\x7fELF\x02\x01\x01"
                    or struct.unpack_from("<HH", header, 16) != (1, 62)):
                raise RuntimeError(name + " is not an x86-64 ELF relocatable object")
    if verify_profile(load_json(args.sdk_profile), "glibc", args.sdk_build) != binding:
        raise RuntimeError("SDK or profile changed during the build")
    match(Path(__file__), recipe_digest)
    match(lock_path, lock_digest)
    for name, checksum in native_headers.items():
        match(root / name, checksum)
    for item in tools.values():
        match(Path(item["path"]), item["sha256"])
    receipt = {"status": status, "source_lock_sha256": lock_digest,
               "builder_sha256": recipe_digest, "sdk_manifest_sha256": manifest_digest,
               "profile_binding": binding, "icu_archive_sha256": icu_lock["archive_sha256"],
               "native_header_sha256": native_headers,
               "target_tools": {name: item["sha256"] for name, item in tools.items()},
               "artifacts": {name: digest(layout / name) for name in artifacts}}
    (output / "manifest.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "icu-archive", "sdk-build", "sdk-profile", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    stages = parser.add_mutually_exclusive_group()
    stages.add_argument("--wtf-stack", dest="stage", action="store_const", const="wtf_stack",
                        help="build only the native WTF stack objects")
    stages.add_argument("--wtf-pthread", dest="stage", action="store_const", const="wtf_pthread",
                        help="build the native WTF stack and pthread lifecycle objects")
    stages.add_argument("--jsc-mutator", dest="stage", action="store_const", const="jsc_mutator",
                        help="build only the JSC mutator admission object")
    parser.set_defaults(stage="layout")
    build(parser.parse_args())


if __name__ == "__main__":
    main()
