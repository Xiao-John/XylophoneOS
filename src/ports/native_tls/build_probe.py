#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the private native TLS guest proof with a signed static glibc SDK."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from build_glibc_program import sha, verify_elf
from glibc_g1_probe import clean_build_environment, tool_identity
from xypm_sdk_profile import source_binding

NET_HEADERS = [
    "src/shared/include/xos/net_service_abi.hpp",
    "src/user/include/xos/net_service_client.hpp",
    "src/user/include/xos/net_transport.hpp",
]
PLATFORM_SOURCES = [
    "src/ports/glibc/sysdeps/xos/clock_gettime.c",
    "src/ports/glibc/sysdeps/xos/getrandom.c",
]


def verify_hashes(parent, files):
    for name, expected in files.items():
        if sha(parent / name) != expected:
            raise ValueError(f"input changed: {parent / name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "sdk", "test-root", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    sdk = args.sdk.resolve(strict=True)
    test_root = args.test_root.resolve(strict=True)
    output = args.output.resolve()
    if test_root.name != "tls_test_root.h":
        parser.error("--test-root must name the generated tls_test_root.h")
    lock_path = HERE / "source_lock.json"
    lock = json.loads(lock_path.read_text())
    if sha(archive) != lock["archive_sha256"]:
        raise ValueError("Mbed TLS archive differs from the upstream lock")
    manifest_path = sdk / "manifest.json"
    manifest_hash = sha(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("status") != "static_sdk_built":
        raise ValueError("a completed, upstream-signature-verified glibc SDK is required")
    sysroot = sdk / "sysroot"
    authentication, _ = source_binding(sdk, sysroot, manifest)
    if authentication["archive_sha256"] != manifest["source_sha256"]:
        raise ValueError("glibc SDK archive differs from its verification evidence")
    verify_hashes(sysroot, manifest["artifacts"])
    verify_hashes(ROOT, {name: manifest["inputs"][name] for name in PLATFORM_SOURCES})
    env, removed = clean_build_environment(os.environ)
    env["LC_ALL"] = "C"
    names = ("gcc", "g++", "as", "ld", "ar", "ranlib", "nm")
    tools = {name: tool_identity("x86_64-elf-" + name) for name in names}
    for name, identity in tools.items():
        if identity.get("version_exit_code") != 0 or (
            identity["sha256"] != manifest["tools"]["x86_64-elf-" + name]["sha256"]
        ):
            raise ValueError(f"x86_64-elf-{name} differs from the signed-source SDK build")
    cmake = tool_identity("cmake")
    if cmake.get("version_exit_code") != 0:
        raise ValueError("CMake is required")

    output.mkdir(parents=True, exist_ok=False)
    extracted = output / "source"
    extracted.mkdir()
    with tarfile.open(archive, "r:bz2") as bundle:
        bundle.extractall(extracted, filter="data")
    upstream = extracted / lock["source_root"]
    verify_hashes(upstream, lock["notices"])
    for name in lock["notices"]:
        target = output / "notices" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((upstream / name).read_bytes())
    cmake_build = output / "mbedtls"
    tool_dir = output / "tools"
    tool_dir.mkdir()
    for name in ("as", "ld"):
        (tool_dir / name).symlink_to(tools[name]["path"])

    def run(name, command):
        log = output / (name + ".log")
        with log.open("w") as stream:
            stream.write(shlex.join(map(str, command)) + "\n")
            stream.flush()
            subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)

    cflags = [
        f"--sysroot={sysroot}", f"-B{tool_dir}/", "-nostdinc",
        "-isystem", str(sysroot / "usr/include"),
        "-isystem", str(sysroot / "usr/lib/compiler-include"), "-D_GNU_SOURCE",
        "-mno-red-zone", "-fno-pie", "-fno-builtin", "-ffunction-sections",
        "-fdata-sections", "-ftls-model=local-exec",
    ]
    configs = {
        "MBEDTLS_USER_CONFIG_FILE": HERE / "mbedtls_xos_config.h",
        "TF_PSA_CRYPTO_USER_CONFIG_FILE": HERE / "tf_psa_crypto_xos_config.h",
    }
    cmake_options = {
        "CMAKE_SYSTEM_NAME": "Generic", "CMAKE_SYSTEM_PROCESSOR": "x86_64",
        "CMAKE_TRY_COMPILE_TARGET_TYPE": "STATIC_LIBRARY", "CMAKE_BUILD_TYPE": "Release",
        "CMAKE_C_COMPILER": tools["gcc"]["path"], "CMAKE_AR": tools["ar"]["path"],
        "CMAKE_RANLIB": tools["ranlib"]["path"], "CMAKE_C_FLAGS": shlex.join(cflags),
        "ENABLE_PROGRAMS": "OFF", "ENABLE_TESTING": "OFF", "GEN_FILES": "OFF",
        "DISABLE_PACKAGE_CONFIG_AND_INSTALL": "ON", **configs,
    }
    browser = ROOT / "src/ports/browser_http"
    sources = [HERE / "platform.c", HERE / "stream.cpp", browser / "http.cpp",
               ROOT / "tests/fixtures/network/native_tls_probe.cpp"]
    helpers = [ROOT / "scripts" / name for name in
               ("build_glibc_program.py", "glibc_g1_probe.py", "xypm_sdk_profile.py")]
    inputs = [*sources, *configs.values(), HERE / "stream.hpp", HERE / "build_probe.py",
              browser / "http.hpp", lock_path, *helpers,
              *(ROOT / path for path in NET_HEADERS + PLATFORM_SOURCES)]
    input_hashes = {path.relative_to(ROOT).as_posix(): sha(path) for path in inputs}
    test_root_hash = sha(test_root)
    run("configure", [cmake["path"], "-S", upstream, "-B", cmake_build,
                      *(f"-D{name}={value}" for name, value in cmake_options.items())])
    run("mbedtls", [cmake["path"], "--build", cmake_build, "--parallel", "2", "--target", "mbedtls"])
    archives = [cmake_build / "library" / f"lib{name}.a" for name in ("mbedtls", "mbedx509")]
    archives.append(cmake_build / "tf-psa-crypto/core/libtfpsacrypto.a")
    includes = [HERE, browser, test_root.parent, upstream / "include",
                upstream / "tf-psa-crypto/include", upstream / "tf-psa-crypto/drivers/builtin/include",
                ROOT / "src/user/include", ROOT / "src/shared/include"]
    objects = []
    for source in sources:
        obj = output / (source.stem + ".o")
        use_c = source.suffix == ".c"
        language = ["-std=gnu11"] if use_c else ["-std=gnu++20", "-nostdinc++", "-fno-exceptions", "-fno-rtti"]
        run(source.stem, [tools["gcc" if use_c else "g++"]["path"], *cflags, *language,
                          "-O2", "-Wall", "-Wextra", "-Werror",
                          *(f'-D{name}="{path}"' for name, path in configs.items()),
                          *(f"-I{path}" for path in includes), "-c", source, "-o", obj])
        objects.append(obj)
    lib = sysroot / "usr/lib"
    elf = output / "native_tls_probe.elf"
    run("link", [tools["gcc"]["path"], f"--sysroot={sysroot}", f"-B{tool_dir}/",
                 "-static", "-no-pie", "-nostdlib", "-Wl,--build-id=none", "-Wl,-z,noexecstack",
                 "-Wl,-z,max-page-size=4096", "-T", sysroot / "user.ld", "-o", elf,
                 *(lib / name for name in ("xos_start.o", "crti.o", "crtbegin.o", "xos_start_c.o")),
                 *objects, "-Wl,--start-group", *archives,
                 *(lib / name for name in ("libc.a", "libm.a", "libxos_terminal.a", "libgcc.a")),
                 "-Wl,--end-group", lib / "crtend.o", lib / "crtn.o"])
    run("symbols", [tools["nm"]["path"], "-n", elf])
    headers = verify_elf(elf)
    verify_hashes(ROOT, input_hashes)
    verify_hashes(sysroot, manifest["artifacts"])
    verify_hashes(sdk, authentication["verification_files"])
    verify_hashes(upstream, lock["notices"])
    if sha(manifest_path) != manifest_hash or sha(test_root) != test_root_hash or (
        sha(archive) != lock["archive_sha256"]
    ):
        raise ValueError("archive, SDK manifest, or test trust anchor changed")
    for identity in (*tools.values(), cmake):
        if sha(Path(identity["path"])) != identity["sha256"]:
            raise ValueError("tool changed during compilation")
    receipt = {
        "status": "linked", "profile": "native_tls_controlled_guest",
        "network_wire_version": 2, "archive_sha256": lock["archive_sha256"],
        "sdk_manifest_sha256": manifest_hash, "glibc_source_sha256": manifest["source_sha256"],
        "glibc_verification_sha256": authentication["report_sha256"],
        "inputs": input_hashes, "test_root_header_sha256": test_root_hash,
        "archives": {str(path.relative_to(output)): sha(path) for path in archives},
        "tools": {**tools, "cmake": cmake}, "sanitized_environment": removed,
        "program_headers": headers, "elf_sha256": sha(elf),
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
