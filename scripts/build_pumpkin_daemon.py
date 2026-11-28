#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the isolated Pumpkin daemon and guest fixture with a recorded XOS SDK."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from toolchain import audit, tool
from xos_app import tree_receipt

root = Path(__file__).resolve().parents[1]
module = "src/user/pumpkin/"
common_cpp = [module + name for name in
              ("account_store.cpp", "service_core.cpp", "daemon_protocol.cpp", "native_ipc.cpp", "native_ipc_client.cpp")]
programs = {"pumpkind.elf": module + "daemon_main.cpp",
            "pumpkin_probe.elf": "tests/fixtures/pumpkin/daemon_guest.cpp"}
storage_programs = {"pumpkin_storage_probe.elf": "tests/fixtures/pumpkin/storage_guest.cpp"}
resource_programs = {"pumpkin_resource_probe.elf": "tests/fixtures/pumpkin/resource_broker_guest.cpp"}
bridge_programs = {**programs, "pumpkin_sealed_broker.elf": module + "resource_broker_main.cpp"}
sdk_headers = [
    ("src/shared/include/xos/", "abi_types.hpp"),
    ("src/shared/include/xos/", "file_abi.hpp"),
    ("src/shared/include/xos/", "process_abi.hpp"),
    ("src/shared/include/xos/", "thread_abi.hpp"),
    ("src/user/include/xos/", "fault_sha256.hpp"),
    ("src/user/include/xos/", "sdk.hpp"),
    ("src/user/include/xos/", "spawn.hpp"),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes(storage_probe=False, resource_probe=False, bridge_probe=False):
    sources, entries = build_inputs(storage_probe, resource_probe, bridge_probe)
    headers = [module + "account_store.hpp"] if storage_probe else [
        module + name for name in ("account_store.hpp", "service_core.hpp", "daemon_protocol.hpp", "native_ipc.hpp")
    ]
    if resource_probe or bridge_probe:
        headers += [module + name for name in ("resource_dispatch.hpp", "sealed_blob.hpp")]
    if bridge_probe:
        headers += [module + name for name in ("resource_bridge.hpp", "resource_broker.hpp", "resource_broker_client.hpp")]
    inputs = sorted([*sources, *entries.values(), *headers, "scripts/build_pumpkin_daemon.py"])
    return {name: sha(root / name) for name in inputs}


def build_inputs(storage_probe, resource_probe=False, bridge_probe=False):
    if storage_probe:
        return [module + "account_store.cpp"], storage_programs
    if resource_probe:
        return common_cpp + [module + name for name in ("resource_dispatch.cpp", "sealed_blob.cpp")], resource_programs
    if bridge_probe:
        entries = ["resource_dispatch.cpp", "sealed_blob.cpp", "resource_bridge.cpp"]
        return common_cpp + [module + name for name in entries], bridge_programs
    return common_cpp, programs


def build(sdk, out, storage_probe=False, resource_probe=False, bridge_probe=False):
    sdk_hash = tree_receipt(sdk)[0]
    for directory, name in sdk_headers:
        if sha(root / directory / name) != sha(sdk / "include/xos" / name):
            raise ValueError(f"SDK header differs from current source: {name}")
    versions = audit()
    sources = source_hashes(storage_probe, resource_probe, bridge_probe)
    sources_cpp, entries = build_inputs(storage_probe, resource_probe, bridge_probe)
    out.relative_to(root / "build")
    out.mkdir(parents=True, exist_ok=False)
    prefix = [tool("g++"), "-std=c++20", "-Os", "-Wall", "-Wextra", "-Werror",
              "-ffreestanding", "-fno-exceptions", "-fno-rtti", "-fno-threadsafe-statics",
              "-fno-use-cxa-atexit", "-fno-unwind-tables", "-fno-asynchronous-unwind-tables",
              "-fno-stack-protector", "-fno-pic", "-fno-pie", "-mno-red-zone", "-mgeneral-regs-only",
              "-nostdinc++", "-ffunction-sections", "-fdata-sections", "-idirafter", sdk / "include",
              "-I", root / "src/user"]
    if bridge_probe:
        if sha(root / "src/user/include/xos/file_client.hpp") != sha(sdk / "include/xos/file_client.hpp"):
            raise ValueError("SDK file client differs from current source")
        prefix += ["-DXOS_PUMPKIN_RESOURCE_BRIDGE=1"]
    linker = ["-nostdlib", "-static", "-no-pie",
              "-Wl,--gc-sections,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096",
              "-T", sdk / "user.ld", sdk / "crt0.o", "-Wl,--start-group", sdk / "lib/libxos.a",
              sdk / "lib/libxos_loader.a", "-Wl,--end-group"]
    commands = []
    for binary, entry in entries.items():
        target = out / binary
        command = [*prefix, *(root / source for source in [*sources_cpp, entry]), *linker, "-o", target]
        subprocess.run(command, check=True, timeout=120)
        strip = [tool("objcopy"), "--strip-debug", target]
        subprocess.run(strip, check=True, timeout=30)
        if target.stat().st_size > 131072:
            raise ValueError(f"ELF exceeds loader image bound: {binary}")
        commands.extend([str(part) for part in items] for items in (command, strip))

    if sources != source_hashes(storage_probe, resource_probe, bridge_probe) or sdk_hash != tree_receipt(sdk)[0]:
        raise ValueError("build inputs changed during compilation")
    profile = "pumpkin-p1-volatile-test"
    if storage_probe:
        profile = "pumpkin-storage-probe"
    elif resource_probe:
        profile = "pumpkin-resource-probe"
    elif bridge_probe:
        profile = "pumpkin-resource-bridge-probe"
    receipt = {"sources": sources, "sdk_tree_sha256": sdk_hash, "toolchain": versions,
               "artifacts": {binary: sha(out / binary) for binary in entries}, "commands": commands,
               "libc_linked": False, "profile": profile}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(out / "receipt.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    probes = parser.add_mutually_exclusive_group()
    probes.add_argument("--storage-probe", action="store_true", help="build only the disposable storage fixture")
    probes.add_argument("--resource-probe", action="store_true", help="build only the sealed-resource guest fixture")
    probes.add_argument("--bridge-probe", action="store_true", help="build the private cross-service resource fixture")
    args = parser.parse_args()
    build(args.sdk.resolve(strict=True), args.output.resolve(), args.storage_probe, args.resource_probe, args.bridge_probe)


if __name__ == "__main__":
    main()
