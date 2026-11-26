#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the ClarkE liteHTML renderer and existing native HTTP provider with glibc Qt Widgets."""

import argparse
from hashlib import sha256
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

PORT = Path(__file__).resolve().parent
BROWSER = PORT.parent
ROOT = PORT.parents[3]
QT = ROOT / "src/ports/qt6"
sys.path.insert(0, str(ROOT / "scripts"))

from build_glibc_program import sha, verify_elf
from glibc_g1_probe import clean_build_environment, tool_identity
from xypm_format import load_json, require
from xypm_sdk_profile import metadata_snapshot, verify_profile

MODULES = ("Core", "Gui", "Widgets", "BundledFreetype", "BundledHarfbuzz", "BundledPcre2", "BundledZLIB")
NETWORK = {"service_wire_version": 2, "service_pid_required": True, "protocol": "HTTP numeric IPv4",
           "same_origin_resources": True, "redirect_limit": 0, "navigation_timeout_ns": 3000000000,
           "navigation_request_limit": 17, "navigation_byte_limit": 2097152}


def prepare_engine(output, lock, archive, env):
    require(sha(archive) == lock["archive_sha256"], "liteHTML archive hash differs from source lock")
    source = output / archive.name.removesuffix(".tar.gz")
    with tarfile.open(archive) as bundle:
        bundle.extractall(output, filter="data")
    files = {path.relative_to(source).as_posix(): sha(path)
             for path in source.rglob("*") if path.is_file()}
    require(files == lock["source_sha256"], "Extracted liteHTML/Gumbo tree differs from source lock")
    patches = [BROWSER / name for name in lock["patches"]]
    commands = [["patch", "-p1", "-d", str(source), "-i", str(patch), "--batch", "--forward"]
                for patch in patches]
    for command in commands:
        subprocess.run(command, env=env, check=True)
    return source, patches, commands


def prepare_tls(args, output, sdk, env):
    tls = BROWSER.parent / "native_tls"
    lock = load_json(tls / "source_lock.json")
    origin = re.fullmatch(r"https://([a-z0-9.-]+)(?::([0-9]{1,5}))?", args.tls_origin)
    require(origin is not None, "Use a lowercase HTTPS origin with a DNS name and optional port")
    host, port_text = origin.groups()
    port = int(port_text) if port_text else 443
    require(len(host) <= 253 and "." in host and 1 <= port <= 65535 and
            all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in host.split(".")), "Invalid HTTPS host or port")
    address = str(ipaddress.IPv4Address(args.tls_address))
    archive = args.tls_archive.resolve(strict=True)
    root_der = args.tls_root_der.resolve(strict=True)
    anchor = root_der.read_bytes()
    require(1 <= len(anchor) <= 4096 and anchor[0] == 0x30, "Expected a bounded DER trust anchor")
    anchor_digest = sha256(anchor).hexdigest()
    config = output / "https"
    config.mkdir()
    root_header = config / "tls_test_root.h"
    root_header.write_text("static constexpr unsigned char tls_test_root[] = {\n    "
                           + ",\n    ".join(", ".join(f"0x{byte:02x}" for byte in anchor[offset:offset + 16])
                                            for offset in range(0, len(anchor), 16)) + "\n};\n")
    origin_header = config / "clarke_https_origin.hpp"
    origin_header.write_text(f'static constexpr char clarke_tls_host[] = "{host}";\n'
                             f'static constexpr char clarke_tls_address[] = "{address}";\n'
                             f'static constexpr unsigned clarke_tls_port = {port};\n')
    target = output / "tls"
    archive_snapshot = config / "mbedtls.tar.bz2"
    shutil.copyfile(archive, archive_snapshot)
    require(sha(archive_snapshot) == lock["archive_sha256"], "Mbed TLS archive differs from the source lock")
    command = [sys.executable, str(tls / "build_probe.py"), "--archive", str(archive_snapshot),
               "--sdk", str(sdk), "--test-root", str(root_header), "--output", str(target)]
    subprocess.run(command, env=env, check=True)
    receipt = load_json(target / "receipt.json")
    require(receipt["sdk_manifest_sha256"] == sha(sdk / "manifest.json") and
            receipt["archive_sha256"] == lock["archive_sha256"] and
            receipt["test_root_header_sha256"] == sha(root_header) and sha(root_der) == anchor_digest and
            sha(archive) == lock["archive_sha256"], "Native TLS build differs from configured input")
    upstream = target / "source" / lock["source_root"]
    libraries = [target / name for name in receipt["archives"]]
    require(all(sha(path) == receipt["archives"][str(path.relative_to(target))] for path in libraries),
            "Native TLS library differs from the build receipt")
    inputs = [archive, archive_snapshot, root_der, root_header, origin_header, target / "receipt.json", PORT / "https.cpp",
              *libraries, *[ROOT / name for name in receipt["inputs"]],
              *[path for path in upstream.rglob("*.h") if path.is_file()]]
    flags = [f"-DXOS_CLARKE_TLS_{key}={path}" for key, path in
             (("BUILD", target), ("UPSTREAM", upstream), ("CONFIG", config))]
    details = {"host": host, "port": port, "ipv4_address": address, "root_der_sha256": anchor_digest,
               "native_tls_receipt_sha256": sha(target / "receipt.json")}
    return flags, inputs, command, details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("sdk-build", "sdk-profile", "qt-build", "qt-prefix", "qt-source", "host-qt", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--tls-origin", help="explicit developer HTTPS origin")
    parser.add_argument("--tls-address", help="pinned IPv4 destination for that origin")
    parser.add_argument("--tls-archive", type=Path, help="locked Mbed TLS source archive")
    parser.add_argument("--tls-root-der", type=Path, help="DER trust anchor for that origin")
    args = parser.parse_args()
    tls_options = (args.tls_origin, args.tls_address, args.tls_archive, args.tls_root_der)
    if any(tls_options) and not all(tls_options):
        parser.error("HTTPS requires origin, destination address, source archive and trust anchor together")
    sdk_build, qt_build, prefix, qt_source, host = (
        path.resolve(strict=True) for path in
        (args.sdk_build, args.qt_build, args.qt_prefix, args.qt_source, args.host_qt))
    sdk = sdk_build / "sysroot"
    output = args.output.resolve()
    if args.jobs < 1 or args.sdk_build.is_symlink() or args.output.is_symlink() or output.exists():
        parser.error("Use a real SDK directory, a fresh output path and a positive job count")
    if any(output.is_relative_to(path) for path in (sdk_build, qt_build, prefix, qt_source, host, BROWSER)):
        parser.error("Put the build output outside the input trees")

    profile = load_json(args.sdk_profile)
    binding = verify_profile(profile, "glibc", sdk_build)
    sdk_binding = profile["sdk_binding"]
    require({"cxx_runtime", "threads"} <= set(profile["features"])
            and "usr/lib/libxos_terminal.a" in sdk_binding["link_artifacts"],
            "The glibc profile must bind C++, threads and the XOS terminal runtime")
    sdk_manifest = sdk_build / "manifest.json"
    manifest, _ = metadata_snapshot(sdk_manifest, sdk_binding["sdk_manifest_sha256"])
    tools = {name: tool_identity(f"x86_64-elf-{name}")
             for name in ("gcc", "g++", "as", "ld", "ar", "ranlib")}
    for name, tool in tools.items():
        require(tool.get("sha256") == manifest["tools"][f"x86_64-elf-{name}"]["sha256"],
                f"x86_64-elf-{name} differs from the SDK build")

    cache_path = qt_build / "CMakeCache.txt"
    cache = dict(line.split("=", 1) for line in cache_path.read_text().splitlines()
                 if line and not line.startswith(("#", "//")) and "=" in line)
    require(cache.get("FEATURE_widgets:BOOL") == "ON"
            and cache.get("CMAKE_HOME_DIRECTORY:INTERNAL") == str(qt_source)
            and cache.get("XOS_GLIBC_SDK:UNINITIALIZED") == str(sdk)
            and cache.get("CMAKE_INSTALL_PREFIX:PATH") == str(prefix),
            "Qt Widgets build must match the source, installed prefix and glibc sysroot")
    archives = {module: prefix / "lib" / f"libQt6{module}.a" for module in MODULES}
    tools_paths = {name: host / "libexec" / name for name in ("moc", "rcc")}
    qt_inputs = archives | tools_paths
    expected = {name: path.resolve(strict=True) for name, path in qt_inputs.items()}
    for path in archives.values():
        require(sha(path) == sha(qt_build / "lib" / path.name),
                f"Installed archive differs from the matching Qt Widgets build: {path.name}")
    env, _ = clean_build_environment(os.environ)
    for name in ("CMAKE_PREFIX_PATH", "Qt6_DIR", "Qt6_ROOT", "QT_ADDITIONAL_PACKAGES_PREFIX_PATH",
                 "QT_ADDITIONAL_HOST_PACKAGES_PREFIX_PATH"):
        env.pop(name, None)
    env["LC_ALL"] = "C"
    version = load_json(QT / "source_lock.json")["version"]
    for name, path in tools_paths.items():
        tool_version = subprocess.check_output([path, "-v"], text=True, stderr=subprocess.STDOUT, env=env)
        require(f"{name} {version}" in tool_version.splitlines(),
                f"Host {name} must report version {version}")

    output.mkdir(parents=True)
    lock_path = BROWSER / "source_lock.json"
    lock = load_json(lock_path)
    archive = BROWSER / lock["archive"]
    engine, patches, commands = prepare_engine(output, lock, archive, env)
    binutils = output / "binutils"
    binutils.mkdir()
    for name in ("as", "ld"):
        (binutils / name).symlink_to(tools[name]["path"])

    http = BROWSER.parent / "browser_http"
    packages = prefix / "lib/cmake"
    package_names = ("Qt6", *(f"Qt6{module}" for module in MODULES))
    font = qt_source / "src/3rdparty/wasm/DejaVuSans.ttf"
    paths = [sdk_manifest, args.sdk_profile.resolve(strict=True), cache_path, font, Path(__file__),
             PORT / "CMakeLists.txt", lock_path, archive, *patches, BROWSER / "main.cpp",
             *BROWSER.glob("*.hpp"), *http.glob("*.cpp"), *http.glob("*.hpp"),
             QT / "glibc/glibc_toolchain.cmake", QT / "glibc/xos_qpa.cmake",
             QT / "cmake/Platform/XOS.cmake", QT / "qpa/qxos.cpp", QT / "qpa/xos.json",
             QT / "aurora/assets/aurora.bmp", QT / "source_lock.json", *qt_inputs.values(),
             *[path for directory in (ROOT / "src/shared/include", ROOT / "src/user/include",
                                      ROOT / "src/user/ssg", QT / "aurora", QT / "runtime")
               for path in directory.glob("**/*") if path.suffix in (".h", ".hpp", ".cpp")],
             *[path for path in engine.rglob("*") if path.is_file()],
             *[path for name in package_names for path in (packages / name).glob("*.cmake")]]
    tls_flags = []
    network_profile = NETWORK
    if args.tls_origin:
        tls_flags, tls_inputs, tls_command, tls_profile = prepare_tls(args, output, sdk_build, env)
        paths.extend(tls_inputs)
        commands.append(tls_command)
        network_profile = {**NETWORK, "protocol": "HTTP numeric IPv4 and controlled HTTPS",
                           "controlled_tls": tls_profile}
    digests = {str(path): sha(path) for path in sorted(paths)}
    includes = ";".join(sdk_binding["cxx_runtime"]["include_directories"])
    build_dir = output / "build"
    configure = ["cmake", "-S", str(PORT), "-B", str(build_dir), "-G", "Ninja",
                 "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF",
                 "-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF",
                 f"-DCMAKE_TOOLCHAIN_FILE={packages / 'Qt6/qt.toolchain.cmake'}",
                 f"-DQT_CHAINLOAD_TOOLCHAIN_FILE={QT / 'glibc/glibc_toolchain.cmake'}",
                 f"-DXOS_QT_PREFIX={prefix}", f"-DXOS_QTBASE_SOURCE={qt_source}", f"-DQT_HOST_PATH={host}",
                 f"-DXOS_CLARKE_LITEHTML_SOURCE={engine}", f"-DXOS_GLIBC_SDK={sdk}", f"-DXOS_GLIBC_TOOLS={binutils}",
                 f"-DXOS_SOURCE_ROOT={ROOT}", f"-DXOS_GLIBC_CXX_INCLUDES={includes}",
                 *(f"-DXOS_GLIBC_{key}={tools[name]['path']}" for key, name in
                   (("CC", "gcc"), ("CXX", "g++"), ("AR", "ar"), ("RANLIB", "ranlib"))),
                 *(f"-D{name}_DIR:PATH={packages / name}" for name in package_names), *tls_flags]
    build = ["cmake", "--build", str(build_dir), "--parallel", str(args.jobs)]
    subprocess.run(configure, env=env, check=True)
    lines = (build_dir / "qt_inputs.txt").read_text().splitlines()
    selected = {name: Path(path).resolve(strict=True) for name, path in (line.split("=", 1) for line in lines)}
    require(selected == expected, "ClarkE selected Qt libraries or generators outside the matched Widgets kit")
    subprocess.run(build, env=env, check=True)
    require({str(path): sha(path) for path in paths} == digests
            and all(path.resolve(strict=True) == expected[name] for name, path in qt_inputs.items())
            and verify_profile(load_json(args.sdk_profile), "glibc", sdk_build) == binding
            and all(sha(Path(tool["path"])) == tool["sha256"] for tool in tools.values()),
            "ClarkE build inputs changed during compilation")

    elf = build_dir / "clarke.elf"
    receipt = {"elf_sha256": sha(elf), "program_headers": verify_elf(elf),
               "commands": [*commands, configure, build], "inputs": digests, "runtime_family": "glibc",
               "sdk_manifest_sha256": sha(sdk_manifest), "sdk_tree_sha256": binding["sdk_tree_sha256"],
               "network_profile": network_profile, "engine_commit": lock["commit"],
               "engine_archives": {name: sha(path) for name, path in
                                   (("litehtml", build_dir / "litehtml/liblitehtml.a"),
                                    ("gumbo", build_dir / "litehtml/src/gumbo/libgumbo.a"))},
               "target_tools": {name: tool["sha256"] for name, tool in tools.items()},
               "guest_qualification": "not_run"}
    elf.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(elf)


if __name__ == "__main__":
    main()
