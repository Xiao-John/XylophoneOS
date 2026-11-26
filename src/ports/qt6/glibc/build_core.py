#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build QtCore in an isolated glibc SDK candidate profile."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

PORT = Path(__file__).resolve().parent
ROOT = PORT.parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from glibc_g1_probe import clean_build_environment, tool_identity
from build_glibc_program import sha, verify_elf
from xypm_format import load_json
from xypm_sdk_profile import metadata_snapshot, verify_profile

FEATURES_OFF = """
testlib concurrent xml gui widgets network sql dbus icu glib stack_protector
intelcet stack_clash_protection poll_select poll_poll poll_ppoll poll_pollts process
processenvironment filesystemwatcher sharedmemory systemsemaphore futimens memmem memrchr
library dlopen system_pcre2 system_zlib
""".split()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "sdk-build", "sdk-profile", "host-qt", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--jobs", default=4, type=int)
    args = parser.parse_args()
    if args.sdk_build.is_symlink():
        parser.error("--sdk-build must not be a symlink")
    sdk_build = args.sdk_build.resolve(strict=True)
    sdk = sdk_build / "sysroot"
    output = args.output.resolve()
    if args.jobs < 1 or args.output.is_symlink() or output.exists():
        parser.error("--jobs must be positive and --output a new directory")
    if output == sdk_build or sdk_build in output.parents:
        parser.error("--output must be outside the SDK build")

    profile = load_json(args.sdk_profile)
    binding = verify_profile(profile, "glibc", sdk_build)
    if not {"cxx_runtime", "threads"} <= set(profile["features"]):
        parser.error("The glibc candidate must contain C++ and threads")
    if "usr/lib/libxos_terminal.a" not in profile["sdk_binding"]["link_artifacts"]:
        parser.error("The glibc candidate must bind libxos_terminal.a for its file runtime")
    sdk_sha = profile["sdk_binding"]["sdk_manifest_sha256"]
    manifest, _ = metadata_snapshot(sdk_build / "manifest.json", sdk_sha)
    tools = {}
    for name in ("gcc", "g++", "as", "ld", "ar", "ranlib"):
        tool = "x86_64-elf-" + name
        details = tool_identity(tool)
        if details.get("sha256") != manifest["tools"][tool]["sha256"]:
            parser.error(f"{tool} differs from the SDK build")
        tools[name] = details

    env, _ = clean_build_environment(os.environ)
    env["LC_ALL"] = "C"
    host = args.host_qt.resolve(strict=True)
    source_lock = json.loads((PORT.parent / "source_lock.json").read_text())
    host_tools = {}
    for name in ("moc", "rcc"):
        executable = host / "libexec" / name
        version = subprocess.check_output([str(executable), "-v"], text=True,
                                          stderr=subprocess.STDOUT, env=env)
        if f"{name} {source_lock['version']}" not in version.splitlines():
            parser.error(f"The host {name} version must match the QtBase source lock")
        host_tools[executable] = sha(executable)

    output.mkdir(parents=True)
    source = output / "source"
    binaries = output / "tools"
    binaries.mkdir()
    for name in ("as", "ld"):
        (binaries / name).symlink_to(tools[name]["path"])
    subprocess.run([sys.executable, str(PORT.parent / "prepare_source.py"),
                    str(args.archive.resolve()), str(source)], check=True, env=env)
    subprocess.run(["patch", "-p1", "-i", str(PORT / "glibc_qtcore.patch")],
                   cwd=source, check=True, env=env)

    includes = ";".join(profile["sdk_binding"]["cxx_runtime"]["include_directories"])
    build = output / "build"
    common = ["-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
              f"-DXOS_GLIBC_SDK={sdk}", f"-DXOS_GLIBC_TOOLS={binaries}",
              f"-DXOS_GLIBC_CXX_INCLUDES={includes}", f"-DXOS_SOURCE_ROOT={ROOT}",
              f"-DXOS_GLIBC_CC={tools['gcc']['path']}", f"-DXOS_GLIBC_CXX={tools['g++']['path']}",
              f"-DXOS_GLIBC_AR={tools['ar']['path']}", f"-DXOS_GLIBC_RANLIB={tools['ranlib']['path']}",
              f"-DQT_HOST_PATH={host}"]
    configure = ["cmake", "-S", str(source), "-B", str(build), *common,
                 f"-DCMAKE_TOOLCHAIN_FILE={PORT / 'glibc_toolchain.cmake'}",
                 "-DQT_QMAKE_TARGET_MKSPEC=xos-g++",
                 "-DBUILD_SHARED_LIBS=OFF", "-DQT_BUILD_EXAMPLES=OFF", "-DQT_BUILD_TESTS=OFF",
                 *[f"-DFEATURE_{feature}=OFF" for feature in FEATURES_OFF]]
    subprocess.run(configure, check=True, env=env)
    subprocess.run(["cmake", "--build", str(build), "--parallel", str(args.jobs),
                    "--target", "Core"], check=True, env=env)

    fixture = ROOT / "tests/fixtures/qt6/glibc"
    fixture_build = output / "fixture"
    # Qt's generated toolchain adds the cross-built prefix without allowing
    # host libraries. Its build-tree find modules still need the source helpers.
    subprocess.run(["cmake", "-S", str(fixture), "-B", str(fixture_build), *common,
                    f"-DCMAKE_TOOLCHAIN_FILE={build / 'lib/cmake/Qt6/qt.toolchain.cmake'}",
                    f"-DCMAKE_MODULE_PATH={source / 'cmake'}"], check=True, env=env)
    subprocess.run(["cmake", "--build", str(fixture_build), "--parallel", str(args.jobs)],
                   check=True, env=env)
    if (verify_profile(load_json(args.sdk_profile), "glibc", sdk_build) != binding
            or any(sha(Path(tool["path"])) != tool["sha256"] for tool in tools.values())
            or any(sha(path) != digest for path, digest in host_tools.items())):
        raise RuntimeError("The SDK or tools changed during the build")
    elf = fixture_build / "core_smoke.elf"
    report = {
        "status": "static_qtcore_linked",
        "qtbase_source_sha256": source_lock["sha256"],
        "sdk_manifest_sha256": sdk_sha,
        "sdk_binding": binding,
        "target_tools": {name: details["sha256"] for name, details in tools.items()},
        "host_tools": {path.name: digest for path, digest in host_tools.items()},
        "qtcore_sha256": sha(build / "lib/libQt6Core.a"),
        "elf_sha256": sha(elf),
        "program_headers": verify_elf(elf),
        "guest_qualification": "not_run",
    }
    (output / "receipt.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
