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
              ("account_store.cpp", "service_core.cpp", "daemon_protocol.cpp", "native_ipc.cpp")]
programs = {"pumpkind.elf": module + "daemon_main.cpp",
            "pumpkin_probe.elf": "tests/fixtures/pumpkin/daemon_guest.cpp"}
inputs = sorted([*common_cpp, *programs.values(), "scripts/build_pumpkin_daemon.py",
                 *(str(source.relative_to(root)) for source in (root / module).glob("*.hpp"))])
sdk_headers = [
    ("src/shared/include/xos/", "abi_types.hpp"),
    ("src/shared/include/xos/", "process_abi.hpp"),
    ("src/shared/include/xos/", "thread_abi.hpp"),
    ("src/user/include/xos/", "fault_sha256.hpp"),
    ("src/user/include/xos/", "sdk.hpp"),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes():
    return {name: sha(root / name) for name in inputs}


def build(sdk, out):
    sdk_hash = tree_receipt(sdk)[0]
    for directory, name in sdk_headers:
        if sha(root / directory / name) != sha(sdk / "include/xos" / name):
            raise ValueError(f"SDK header differs from current source: {name}")
    versions = audit()
    sources = source_hashes()
    out.relative_to(root / "build")
    out.mkdir(parents=True, exist_ok=False)
    prefix = [tool("g++"), "-std=c++20", "-Os", "-Wall", "-Wextra", "-Werror",
              "-ffreestanding", "-fno-exceptions", "-fno-rtti", "-fno-threadsafe-statics",
              "-fno-use-cxa-atexit", "-fno-unwind-tables", "-fno-asynchronous-unwind-tables",
              "-fno-stack-protector", "-fno-pic", "-fno-pie", "-mno-red-zone", "-mgeneral-regs-only",
              "-nostdinc++", "-ffunction-sections", "-fdata-sections", "-idirafter", sdk / "include",
              "-I", root / "src/user"]
    linker = ["-nostdlib", "-static", "-no-pie",
              "-Wl,--gc-sections,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096",
              "-T", sdk / "user.ld", sdk / "crt0.o", "-Wl,--start-group", sdk / "lib/libxos.a",
              sdk / "lib/libxos_loader.a", "-Wl,--end-group"]
    commands = []
    for binary, entry in programs.items():
        target = out / binary
        command = [*prefix, *(root / source for source in [*common_cpp, entry]), *linker, "-o", target]
        subprocess.run(command, check=True, timeout=120)
        strip = [tool("objcopy"), "--strip-debug", target]
        subprocess.run(strip, check=True, timeout=30)
        if target.stat().st_size > 131072:
            raise ValueError(f"ELF exceeds loader image bound: {binary}")
        commands.extend([str(part) for part in items] for items in (command, strip))

    if sources != source_hashes() or sdk_hash != tree_receipt(sdk)[0]:
        raise ValueError("build inputs changed during compilation")
    receipt = {"sources": sources, "sdk_tree_sha256": sdk_hash, "toolchain": versions,
               "artifacts": {binary: sha(out / binary) for binary in programs}, "commands": commands,
               "libc_linked": False, "profile": "pumpkin-p1-volatile-test"}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(out / "receipt.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.sdk.resolve(strict=True), args.output.resolve())


if __name__ == "__main__":
    main()
