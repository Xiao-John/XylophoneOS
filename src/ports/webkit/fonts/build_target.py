#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the standalone font dependencies used by WebCore on XOS."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

port = Path(__file__).resolve().parent
webkit = port.parent
root = webkit.parents[2]
sys.path.insert(0, str(root / "scripts"))
sys.path.insert(0, str(webkit))
from target_inputs import recheck_inputs, target_inputs
from build_glibc_program import verify_elf
from glibc_g1_probe import clean_build_environment, tool_identity
from xypm_format import load_json
from xypm_sdk_profile import metadata_snapshot, verify_profile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def match(path, expected):
    if digest(path) != expected:
        raise ValueError(f"input digest mismatch: {path.name}")


def build(args):
    qt_lock = root / "src/ports/qt6/source_lock.json"
    webkit_lock = webkit / "source_lock.json"
    qt = load_json(qt_lock)
    icu_lock = load_json(webkit_lock)["llint_icu"]
    recipe = digest(Path(__file__))
    driver_source = webkit / "icu/xos-compiler"
    driver_hash = digest(driver_source)
    fixture = root / "tests/fixtures/webkit/font_stack.cpp"
    fixture_hash = digest(fixture)
    lock_hashes = {str(path.relative_to(root)): digest(path) for path in (qt_lock, webkit_lock)}
    match(args.qtbase_archive, qt["sha256"])
    profile = load_json(args.sdk_profile)
    binding = verify_profile(profile, "glibc", args.sdk_build)
    if "cxx_runtime" not in profile["features"]:
        raise ValueError("the font build requires a complete glibc C/C++ SDK")
    icu_inputs = {}
    if args.icu_target:
        _, icu_inputs = target_inputs(args.icu_target, 'static_icu_built', binding['sdk_tree_sha256'],
                                     artifact_root=args.icu_target / 'install', headers='include')
        icu_binding = {'icu_target_manifest_sha256': icu_inputs[args.icu_target / 'manifest.json']}
    else:
        match(args.icu_archive, icu_lock["archive_sha256"])
        if binding["sdk_tree_sha256"] != icu_lock["sdk_tree_sha256"]:
            raise ValueError("the legacy ICU archive requires its exact historical SDK")
        icu_binding = {'icu_archive_sha256': icu_lock['archive_sha256']}
    manifest, sdk_hash = metadata_snapshot(args.sdk_build / "manifest.json",
                                          profile["sdk_binding"]["sdk_manifest_sha256"])
    tools = {}
    for suffix in ("gcc", "g++", "as", "ld", "ar", "ranlib"):
        name = "x86_64-elf-" + suffix
        identity = tool_identity(name)
        if identity.get("sha256") != manifest["tools"][name]["sha256"]:
            raise ValueError(f"{name} differs from the glibc SDK build")
        tools[suffix] = identity

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    env, _ = clean_build_environment(os.environ)
    env["LC_ALL"] = "C"

    def run(stage, command):
        log = output / (stage + ".log")
        with log.open("a") as stream:
            result = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f"{stage} failed; see {log}")

    source, icu, drivers, objects, prefix = (output / name for name in
                                             ("source", "icu", "drivers", "objects", "prefix"))
    for directory in (source, icu, drivers, objects, prefix / "include", prefix / "lib"):
        directory.mkdir(parents=True)
    archive_root = "qtbase-everywhere-src-" + qt["version"]
    vendor = archive_root + "/src/3rdparty/"
    run("unpack_qt", ["tar", "-xJf", args.qtbase_archive, "-C", source,
                      vendor + "freetype", vendor + "harfbuzz-ng",
                      vendor + "wasm/DejaVuSans.ttf", vendor + "wasm/DEJAVU-LICENSE"])
    if args.icu_target:
        icu = args.icu_target / 'install'
    else:
        run("unpack_icu", ["tar", "--zstd", "-xf", args.icu_archive, "-C", icu])
        for name, checksum in icu_lock["artifacts"].items():
            match(icu / name, checksum)
    for driver in ("cc", "cxx"):
        (drivers / driver).symlink_to(driver_source)
    for name in ("as", "ld"):
        (drivers / f"x86_64-elf-{name}").symlink_to(tools[name]["path"])
    includes = drivers / "cxx-includes.txt"
    includes.write_text("\n".join(profile["sdk_binding"]["cxx_runtime"]["include_directories"]) + "\n")
    env.update(XOS_ICU_SDK=str(args.sdk_build / "sysroot"), XOS_ICU_CXX_INCLUDES=str(includes),
               XOS_ICU_CC=tools["gcc"]["path"], XOS_ICU_CXX=tools["g++"]["path"])

    freetype = source / vendor / "freetype"
    harfbuzz = source / vendor / "harfbuzz-ng"
    font = source / archive_root / "src/3rdparty/wasm/DejaVuSans.ttf"
    sources = re.search(r"(?ms)^set\(BASE_SRCS\n(.*?)^\)", (freetype / "CMakeLists.txt").read_text())
    if not sources:
        raise ValueError("the locked FreeType source list is missing")
    freetype_sources = sources[1].split() + ["src/base/ftdebug.c", "src/base/ftsystem.c"]
    freetype_objects = []
    flags = ["-B" + str(drivers) + "/", "-O2", "-ffunction-sections", "-fdata-sections",
             f"-ffile-prefix-map={output}=.", f"-ffile-prefix-map={root}=."]
    for name in freetype_sources:
        obj = objects / (Path(name).stem + ".o")
        run("freetype", [drivers / "cc", *flags, "-DFT2_BUILD_LIBRARY", "-I", freetype / "include",
                         "-c", freetype / name, "-o", obj])
        freetype_objects.append(obj)

    hb_flags = [*flags, "-I", freetype / "include", "-I", icu / "include", "-I", harfbuzz / "src"]
    hb_object, hb_icu_object = objects / "harfbuzz.o", objects / "harfbuzz-icu.o"
    run("harfbuzz", [drivers / "cxx", *hb_flags, "-std=c++17", "-DHAVE_FREETYPE", "-DHAVE_PTHREAD",
                     "-c", harfbuzz / "src/harfbuzz.cc", "-o", hb_object])
    run("harfbuzz_icu", [drivers / "cxx", *hb_flags, "-std=c++17", "-DHAVE_ICU",
                         "-c", harfbuzz / "src/hb-icu.cc", "-o", hb_icu_object])
    for archive, members in (("freetype", freetype_objects), ("harfbuzz", [hb_object]),
                             ("harfbuzz-icu", [hb_icu_object])):
        run("archives", [tools["ar"]["path"], "rcsD", prefix / f"lib/lib{archive}.a", *members])
    shutil.copytree(freetype / "include", prefix / "include/freetype2")
    headers = prefix / "include/harfbuzz"
    headers.mkdir()
    for header in sorted((harfbuzz / "src").glob("hb*.h")):
        shutil.copyfile(header, headers / header.name)

    probe = output / "font_stack.elf"
    libraries = [prefix / f"lib/lib{name}.a" for name in ("harfbuzz-icu", "harfbuzz", "freetype")]
    run("link_probe", [drivers / "cxx", *hb_flags, fixture, *libraries,
                       icu / "lib/libicuuc.a", icu / "lib/libicudata.a", "-o", probe])
    verify_elf(probe)
    shutil.copyfile(font, output / "sample.ttf")
    notices = prefix / "share/licenses"
    for library, directory, names in (
        ("freetype", freetype, ("LICENSE.txt", "docs/FTL.TXT", "docs/GPLv2.TXT",
                                "BDF-LICENSE.txt", "PCF-LICENSE.txt", "ZLIB-LICENSE.txt")),
        ("harfbuzz", harfbuzz, ("COPYING",)),
        ("dejavu", font.parent, ("DEJAVU-LICENSE",)),
    ):
        for name in names:
            destination = notices / library / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(directory / name, destination)

    match(args.qtbase_archive, qt["sha256"])
    if args.icu_archive:
        match(args.icu_archive, icu_lock["archive_sha256"])
    recheck_inputs(icu_inputs)
    verify_profile(profile, "glibc", args.sdk_build)
    for name, checksum in lock_hashes.items():
        match(root / name, checksum)
    match(Path(__file__), recipe)
    match(driver_source, driver_hash)
    match(fixture, fixture_hash)
    for tool in tools.values():
        match(Path(tool["path"]), tool["sha256"])
    artifacts = sorted(path for path in prefix.rglob("*") if path.is_file()) + [probe, output / "sample.ttf"]
    receipt = {"status": "target_font_stack_linked", "source_locks": lock_hashes, "recipe_sha256": recipe,
               "qtbase_archive_sha256": qt["sha256"], **icu_binding,
               "sdk_manifest_sha256": sdk_hash, "profile_binding": binding, "fixture_sha256": fixture_hash,
               "driver_sha256": driver_hash,
               "target_tools": {name: item["sha256"] for name, item in tools.items()},
               "artifacts": {path.relative_to(output).as_posix(): digest(path) for path in artifacts}}
    (output / "manifest.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("qtbase-archive", "sdk-build", "sdk-profile", "output"):
        parser.add_argument("--" + name, required=True, type=lambda path: Path(path).resolve())
    icu = parser.add_mutually_exclusive_group(required=True)
    icu.add_argument('--icu-target', type=lambda path: Path(path).resolve())
    icu.add_argument('--icu-archive', type=lambda path: Path(path).resolve())
    build(parser.parse_args())
