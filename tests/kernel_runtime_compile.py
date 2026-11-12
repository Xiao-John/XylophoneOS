# SPDX-License-Identifier: Apache-2.0
"""Strict host object checks with declaration-only generated-image substitutes.

Uses the repository compiler flags and the selected host CXX. This deliberately
does not link a kernel, build image payloads, change the toolchain lock or claim
target/guest qualification. Every substitute is an extern declaration.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "scripts"))
from toolchain import COMMON_FLAGS as common_flags, X86_FLAGS as x86_flags


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=repo_root / "build/kernel_runtime_host")
    args = parser.parse_args()
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    declarations = output / "declarations"
    declarations.mkdir(exist_ok=True)
    names = ("heartbeat", "spinner", "receiver", "sender", "probe", "quitter")
    (declarations / "user_blobs.hpp").write_text(
        "#pragma once\n#include <xos/types.hpp>\nnamespace xos::user_blobs {\n" +
        "\n".join(f"extern const u8 {name}[]; extern const u32 {name}_size;" for name in names) + "\n}\n")
    (declarations / "user_images.hpp").write_text(
        "#pragma once\n#include <xos/types.hpp>\nnamespace xos::user_images {\n"
        "struct segment { u64 address, offset, files, memory; u32 permissions; };\n"
        "struct module { const char* name; const u8* bytes; u64 size; };\n"
        "extern const u8 supervisor[], files[];\n"
        "extern const segment bootstrap_segments[1], bootstrap_segments_files[1];\n"
        "extern const u64 bootstrap_entry, bootstrap_entry_files;\n"
        "extern const module catalog[1];\n}\n")
    (declarations / "build_info.hpp").write_text(
        '#pragma once\n#define XOS_BUILD_ID "host-declarations-only"\n'
        '#define XOS_EASTER_EGGS 1\n#define XOS_CAPACITY_PROBE 0\n#define XOS_CLOCK_IRQ_PROBE 0\n')
    cxx = os.environ.get("CXX", "c++")
    include = ["-I", str(declarations)]
    for folder in ("src/kernel/include", "src/kernel", "src/shared/include"):
        include += ["-I", str(repo_root / folder)]
    checks = []
    profiles = (("default", 0, 0, 1), ("eager", 0, 0, 0), ("vm1", 1, 0, 1), ("cow1", 1, 1, 1))
    for name, vm, cow, normal_cow in profiles:
        command = [cxx, *common_flags, *x86_flags, *include,
                   f"-DXOS_VM1_PROBE={vm}", f"-DXOS_COW1_PROBE={cow}", f"-DXOS_COW_FORK={normal_cow}",
                   "-c", str(repo_root / "src/kernel/arch/x86_64/tasks.cpp"),
                   "-o", str(output / f"tasks_{name}.o")]
        result = subprocess.run(command, capture_output=True, text=True)
        checks.append({"name": name, "command": command, "returncode": result.returncode, "stderr": result.stderr})
    for name in ("paging", "cpu_time", "exceptions"):
        command = [cxx, *common_flags, *x86_flags, *include,
                   "-c", str(repo_root / f"src/kernel/arch/x86_64/{name}.cpp"), "-o", str(output / f"{name}.o")]
        result = subprocess.run(command, capture_output=True, text=True)
        checks.append({"name": name, "command": command, "returncode": result.returncode, "stderr": result.stderr})
    report = {"scope": "host objects only; declaration image headers; no target link or guest",
              "compiler": subprocess.check_output([cxx, "--version"], text=True), "checks": checks}
    (output / "compile.json").write_text(json.dumps(report, indent=2) + "\n")
    for check in checks:
        print(check["name"], "PASS" if check["returncode"] == 0 else "FAIL", check["stderr"])
    raise SystemExit(int(any(check["returncode"] for check in checks)))


if __name__ == "__main__":
    main()
