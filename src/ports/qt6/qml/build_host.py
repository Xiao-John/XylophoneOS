#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build pinned, native static QtCore/Qml and E18 host generators in a fresh directory."""

import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
import subprocess
import tarfile

PORT = Path(__file__).resolve().parent


def extract_source(stream, root, destination):
    with tarfile.open(fileobj=stream, mode="r:xz") as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            if name.parts == (root,) and member.isdir():
                continue
            if (name.parts[:1] != (root,) or len(name.parts) < 2
                    or ".." in name.parts or not (member.isfile() or member.isdir())):
                raise ValueError(f"unexpected archive member: {member.name}")
            member.name = str(PurePosixPath(*name.parts[1:]))
            archive.extract(member, destination, filter="data")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qtbase", required=True, type=Path)
    parser.add_argument("--qtdeclarative", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="fresh host-only directory")
    parser.add_argument("--jobs", default=4, type=int)
    parser.add_argument("--apple-clt", action="store_true",
                        help="allow a macOS Command Line Tools build without full Xcode")
    parser.add_argument("--apple-sdk", type=Path, help="explicit macOS SDK directory")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    if args.apple_sdk and (platform.system() != "Darwin" or not args.apple_sdk.is_dir()):
        parser.error("--apple-sdk must refer to a macOS SDK directory on a Darwin host")
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        parser.error("--output must not exist")
    base = json.loads((PORT.parent / "source_lock.json").read_text())
    declarative = json.loads((PORT / "source_lock.json").read_text())
    if (base["version"] != declarative["version"]
            or base["tag_commit"] != declarative["qtbase_commit"]):
        parser.error("QtBase and QtDeclarative locks disagree")

    with ExitStack() as stack:
        archives = [(stack.enter_context(path.open("rb")), lock)
                    for path, lock in ((args.qtbase, base), (args.qtdeclarative, declarative))]
        for stream, lock in archives:
            if hashlib.file_digest(stream, "sha256").hexdigest() != lock["sha256"]:
                parser.error(f'{lock["component"]} archive SHA-256 mismatch')
            stream.seek(0)
        output.mkdir(parents=True)
        for stream, lock in archives:
            component = lock["component"]
            extract_source(stream, f'{component}-everywhere-src-{lock["version"]}',
                           output / "source" / component)

    patch = PORT.parent / "patches/0010-xos-host-arm64-acle.patch"
    host_patches = {}
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        subprocess.run(["patch", "-p1", "-i", str(patch)],
                       cwd=output / "source/qtbase", check=True)
        host_patches[patch.name] = hashlib.sha256(patch.read_bytes()).hexdigest()
    prefix = output / "prefix"
    common = ["-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
              f"-DCMAKE_INSTALL_PREFIX={prefix}", "-DBUILD_SHARED_LIBS=OFF",
              "-DQT_BUILD_EXAMPLES=OFF", "-DQT_BUILD_TESTS=OFF",
              "-DQT_BUILD_BENCHMARKS=OFF"]
    if args.apple_clt:
        common.append("-DQT_FORCE_WARN_APPLE_SDK_AND_XCODE_CHECK=ON")
    if args.apple_sdk:
        common.append(f"-DCMAKE_OSX_SYSROOT={args.apple_sdk.resolve()}")
    base_off = ("gui", "widgets", "network", "opengl", "sql", "dbus", "concurrent",
                "testlib", "icu", "framework", "system_pcre2", "system_zlib")
    modules = (("qtbase", [f"-DFEATURE_{feature}=OFF" for feature in base_off]),
               ("qtdeclarative", [f"-DCMAKE_PREFIX_PATH={prefix}",
                                  "-DFEATURE_qml_jit=OFF", "-DFEATURE_qml_debug=OFF"]))
    for component, options in modules:
        build = output / f"{component}_build"
        subprocess.run(["cmake", "-S", str(output / "source" / component),
                        "-B", str(build), *common, *options], check=True)
        subprocess.run(["cmake", "--build", str(build), "--parallel", str(args.jobs)], check=True)
        subprocess.run(["cmake", "--install", str(build)], check=True)

    receipt = {"profile": "qt_e18_static_host", "version": base["version"],
               "platform": platform.system(), "machine": platform.machine(),
               "apple_sdk": args.apple_sdk.resolve().name if args.apple_sdk else None,
               "archives": {lock["component"]: lock["sha256"] for _, lock in archives},
               "qtbase_patches": host_patches, "guest_qualification": "not_run"}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
