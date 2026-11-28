# SPDX-License-Identifier: Apache-2.0
"""Test the production bounded DHCP policy/lease helper; no lwIP or guest claim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sanitize", action="store_true")
    options = parser.parse_args()
    output = options.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cxx = shutil.which(os.environ.get("CXX", "c++"))
    target_cxx = shutil.which(os.environ.get("XOS_CXX", "x86_64-elf-g++"))
    if not cxx or not target_cxx:
        parser.error("host CXX and target XOS_CXX are required; use the Preview 2 SDK")
    source = root / "src/user/network/dhcp_policy.cpp"
    fixture = root / "tests/fixtures/network/dhcp_policy_host.cpp"
    inputs = [Path(__file__).resolve(), source, fixture,
              root / "src/user/network/dhcp_policy.hpp", root / "src/shared/include/xos/abi_types.hpp"]
    hashes = {str(path.relative_to(root)): sha256(path) for path in inputs}
    strict = ["-std=c++20", "-Wall", "-Wextra", "-Werror", "-Wshadow", "-O1", "-g",
              "-I", str(root / "src/shared/include"), "-I", str(root / "src/user")]
    sanitizers = ["-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                  "-fno-omit-frame-pointer"] if options.sanitize else []
    binary = output / "dhcp_policy_host"
    target = output / "dhcp_policy_target.o"
    commands = [
        [cxx, *strict, *sanitizers, str(fixture), str(source), "-o", str(binary)],
        [target_cxx, *strict, "-ffreestanding", "-fno-exceptions", "-fno-rtti", "-nostdinc++",
         "-mno-red-zone", "-c", str(source), "-o", str(target)],
    ]
    for index, command in enumerate(commands):
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        (output / f"compile_{index}.log").write_text(result.stdout + result.stderr)
        if result.returncode:
            sys.stderr.write(result.stdout + result.stderr)
            raise RuntimeError(f"DHCP compile failed: {index}")
    listing = subprocess.run([str(binary), "--list"], capture_output=True, text=True, timeout=10)
    (output / "list.log").write_text(listing.stdout + listing.stderr)
    if listing.returncode:
        sys.stderr.write(listing.stderr)
        raise RuntimeError("DHCP scenario listing failed")
    scenarios = listing.stdout.splitlines()
    rows = []
    for name in scenarios:
        result = subprocess.run([str(binary), name], capture_output=True, text=True, timeout=30)
        (output / f"{name}.log").write_text(result.stdout + result.stderr)
        rows.append({"name": name, "returncode": result.returncode})
        sys.stdout.write(result.stdout)
        if result.returncode:
            sys.stderr.write(result.stderr)
            raise RuntimeError(f"DHCP scenario failed: {name}")
    for name, expected in hashes.items():
        if sha256(root / name) != expected:
            raise RuntimeError(f"Input changed while tests ran: {name}; rerun required")
    receipt = {
        "qualification": "production_helper_host_and_target_object",
        "lwip_integration": "not_run", "guest_qualification": "not_run",
        "sdk_profile": "xos-sdk-preview-2-linux-x86_64",
        "commands": commands, "inputs": hashes, "scenarios": rows,
        "mutation_iterations": 20000,
        "compiler": subprocess.check_output([cxx, "--version"], text=True).splitlines()[0],
        "target_compiler": subprocess.check_output([target_cxx, "--version"], text=True).splitlines()[0],
        "target_machine": subprocess.check_output([target_cxx, "-dumpmachine"], text=True).strip(),
        "python": sys.version.splitlines()[0],
        "sanitizers": ["address", "undefined"] if options.sanitize else [],
        "asan_options": os.environ.get("ASAN_OPTIONS", ""),
        "leak_sanitizer": "not_run",
        "artifacts": {binary.name: sha256(binary), target.name: sha256(target)},
    }
    (output / "result.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"DHCP_POLICY_PRODUCTION_SCENARIOS_PASSED={len(rows)}")
    print("DHCP_POLICY_TARGET_FREESTANDING_COMPILE=PASSED")


if __name__ == "__main__":
    main()
