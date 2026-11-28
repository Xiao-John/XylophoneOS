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
    for name in ("archive", "sdk", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--test-root", type=Path)
    parser.add_argument("--trust-fixtures", type=Path,
                        help="explicit generated trust-store guest fixture header")
    parser.add_argument('--xypm-profile-id', help='build the GHCR companion for this package profile')
    parser.add_argument('--xypm-fixture-port', type=int, help='test-only GHCR companion port')
    parser.add_argument('--xypm-installer', action='store_true', help='build the paired glibc installer instead of the fetcher')
    args = parser.parse_args()
    if args.xypm_installer and not args.xypm_profile_id:
        parser.error('--xypm-installer requires a profile ID')
    if args.xypm_fixture_port is not None and (not args.xypm_profile_id or not 1024 <= args.xypm_fixture_port <= 65535):
        parser.error('--xypm-fixture-port requires a GHCR profile and an unprivileged TCP port')
    if args.xypm_profile_id:
        import re
        if not re.fullmatch(r'[a-z][a-z0-9_.-]{0,79}', args.xypm_profile_id):
            parser.error('invalid xypm profile ID')
        if args.trust_fixtures:
            parser.error('GHCR companion does not use TLS test fixtures')
    archive = args.archive.resolve(strict=True)
    sdk = args.sdk.resolve(strict=True)
    if not args.test_root and not args.xypm_profile_id:
        parser.error('--test-root is required for the TLS probe')
    test_root = args.test_root.resolve(strict=True) if args.test_root else None
    trust_fixtures = args.trust_fixtures.resolve(strict=True) if args.trust_fixtures else None
    if trust_fixtures and trust_fixtures.name != 'tls_trust_fixtures.hpp':
        parser.error('--trust-fixtures must name tls_trust_fixtures.hpp')
    output = args.output.resolve()
    if test_root and test_root.name != "tls_test_root.h":
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
    sources = [HERE / "platform.c", HERE / "stream.cpp", HERE / "trust_store.cpp", browser / "http.cpp",
               browser / "transport.cpp", browser / "https_transport.cpp",
               ROOT / ("src/user/programs/xypm_ghcr.cpp" if args.xypm_profile_id else
                       "tests/fixtures/network/native_tls_probe.cpp")]
    program_headers = []
    if args.xypm_installer:
        programs = ROOT / 'src/user/programs'
        sources += [programs / 'xypm.cpp', programs / 'xypm_recover.cpp',
                   ROOT / 'src/user/sdk/file_client.cpp', ROOT / 'src/user/sdk/text.cpp',
                   ROOT / 'src/user/arch/x86_64/syscall.cpp']
        program_headers = [programs / name for name in ('xypm_journal.hpp', 'xypm_repository.hpp',
                           'xypm_repository_io.hpp', 'xypm_transaction_impl.hpp')]
        (output / 'xypm_profile.hpp').write_text(
            '#pragma once\n#define XYP_GLIBC_RUNTIME 1\n#define XYP_NATIVE_C_HEADERS 1\n'
            '#define XYP_PACKAGE_FEATURES(name) (!::strcmp(name, "stdio") || !::strcmp(name, "heap") || '
            '!::strcmp(name, "file_io") || !::strcmp(name, "directories") || !::strcmp(name, "static_tls"))\n')
        cflags.extend(('-DXYP_NATIVE_C_HEADERS=1', '-DXYP_RECOVERY_LIBRARY=1', '-DXYP_GHCR_LINKED=1',
                       '-Wno-unused-parameter', '-Wno-misleading-indentation', '-Wno-clobbered'))
    if args.xypm_profile_id:
        cflags.append(f'-DXYP_PACKAGE_PROFILE_ID="{args.xypm_profile_id}"')
    if args.xypm_fixture_port:
        cflags.append(f'-DXYP_GHCR_FIXTURE_PORT={args.xypm_fixture_port}')
    helpers = [ROOT / "scripts" / name for name in
               ("build_glibc_program.py", "glibc_g1_probe.py", "xypm_sdk_profile.py")]
    inputs = [*sources, *program_headers, *configs.values(), HERE / "stream.hpp", HERE / "trust_store.hpp", HERE / "build_probe.py",
              browser / "http.hpp", browser / "transport.hpp", browser / "https_transport.hpp", lock_path, *helpers,
              *(ROOT / path for path in NET_HEADERS + PLATFORM_SOURCES)]
    if args.xypm_profile_id:
        inputs.extend((ROOT / 'src/user/programs/xypm_native.hpp',
                       ROOT / 'src/user/include/xos/text.hpp',
                       ROOT / 'src/user/include/xos/unicode_width_data.hpp'))
    input_hashes = {path.relative_to(ROOT).as_posix(): sha(path) for path in inputs}
    test_root_hash = sha(test_root) if test_root else None
    trust_hash = sha(trust_fixtures) if trust_fixtures else None
    run("configure", [cmake["path"], "-S", upstream, "-B", cmake_build,
                      *(f"-D{name}={value}" for name, value in cmake_options.items())])
    run("mbedtls", [cmake["path"], "--build", cmake_build, "--parallel", "2", "--target", "mbedtls"])
    archives = [cmake_build / "library" / f"lib{name}.a" for name in ("mbedtls", "mbedx509")]
    archives.append(cmake_build / "tf-psa-crypto/core/libtfpsacrypto.a")
    includes = [output, HERE, browser, upstream / "include",
                upstream / "tf-psa-crypto/include", upstream / "tf-psa-crypto/drivers/builtin/include",
                ROOT / "src/user/include", ROOT / "src/shared/include"]
    if test_root:
        includes.append(test_root.parent)
    if trust_fixtures:
        includes.append(trust_fixtures.parent)
        cflags.append('-DXOS_TLS_TRUST_STORE_PROBE=1')
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
    elf = output / ("xypm.elf" if args.xypm_installer else
                    "xypm-ghcr.elf" if args.xypm_profile_id else "native_tls_probe.elf")
    run("link", [tools["gcc"]["path"], f"--sysroot={sysroot}", f"-B{tool_dir}/",
                 "-static", "-no-pie", "-nostdlib", "-Wl,--build-id=none", "-Wl,--gc-sections", "-Wl,-z,noexecstack",
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
    if sha(manifest_path) != manifest_hash or (test_root and sha(test_root) != test_root_hash) or (
        sha(archive) != lock["archive_sha256"]
    ):
        raise ValueError("archive, SDK manifest, or test trust anchor changed")
    if trust_fixtures and sha(trust_fixtures) != trust_hash:
        raise ValueError('trust-store fixture changed')
    for identity in (*tools.values(), cmake):
        if sha(Path(identity["path"])) != identity["sha256"]:
            raise ValueError("tool changed during compilation")
    receipt = {
        "status": "linked", "profile": args.xypm_profile_id or "native_tls_controlled_guest",
        "network_wire_version": 2, "xypm_installer": args.xypm_installer, "archive_sha256": lock["archive_sha256"],
        "sdk_manifest_sha256": manifest_hash, "glibc_source_sha256": manifest["source_sha256"],
        "glibc_verification_sha256": authentication["report_sha256"],
        "inputs": input_hashes, "test_root_header_sha256": test_root_hash,
        "archives": {str(path.relative_to(output)): sha(path) for path in archives},
        "tools": {**tools, "cmake": cmake}, "sanitized_environment": removed,
        "program_headers": headers, "elf_sha256": sha(elf),
        **({'xypm_fixture_port': args.xypm_fixture_port} if args.xypm_fixture_port else {}),
        **({'trust_fixture_sha256': trust_hash} if trust_fixtures else {}),
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
