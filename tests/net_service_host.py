# SPDX-License-Identifier: Apache-2.0
"""Run production N2 and pinned lwIP against a packet-level Ethernet peer.

Explicit verified inputs are required; no download or guest qualification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "scripts"))
from lwip_service_build import core_sources, ipv4_sources, prepare_source, source_input_paths


def run(arguments):
    subprocess.run(arguments, check=True, timeout=90)


def build_and_test(options, output):
    output.mkdir(parents=True, exist_ok=True)
    lock = json.loads((root / "src/ports/lwip/source_lock.json").read_text())
    source = prepare_source(root, options.archive, output / "source")
    includes = ["-I", str(root / "src/user/network/include"),
                "-I", str(root / "src/ports/lwip/include"), "-I", str(source / "src/include"),
                "-I", str(root / "src/shared/include"), "-I", str(root / "src/user")]
    sanitizer = ["-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                 "-fno-omit-frame-pointer"] if options.sanitize else []
    common = ["-O1" if options.sanitize else "-O2", "-g", *sanitizer, *includes]
    cxx = os.environ.get("CXX", "c++")
    cc = os.environ.get("CC", "cc")
    fixture = root / "tests/fixtures/network/service_host.cpp"
    loop_fixture = root / "tests/fixtures/network/service_loop_host.cpp"
    production_sources = [root / "src/user/network/service_core.cpp", root / "src/user/network/lwip_stack.cpp"]
    compile_inputs = [(root / "src/user/network/service_loop.cpp", "loop", []),
                      (root / "src/user/programs/net_service.cpp", "entry_raw", []),
                      (root / "src/user/programs/net_service.cpp", "entry_native", ["-DXOS_NET_STACK=1"])]
    own_inputs = [Path(__file__).resolve(), fixture, loop_fixture, *production_sources, *(item for item, _, _ in compile_inputs),
                  root / "src/user/network/service_core.hpp", root / "src/user/network/lwip_stack.hpp",
                  root / "src/user/network/egress_policy.hpp",
                  root / "src/user/network/service_loop.hpp", root / "src/shared/include/xos/net_service_abi.hpp",
                  root / "src/user/network/include/lwipopts.h", root / "src/ports/lwip/include/lwipopts.h",
                  root / "src/user/network/include/arch/cc.h", root / "src/ports/lwip/include/arch/cc.h",
                  root / "scripts/lwip_service_build.py", *source_input_paths(root)]
    input_hashes = {str(item.relative_to(root)): hashlib.sha256(item.read_bytes()).hexdigest()
                    for item in sorted(set(own_inputs))}
    sources = [source / "src/core" / name for name in core_sources]
    sources += [source / "src/core/ipv4" / name for name in ipv4_sources]
    sources += [source / "src/netif/ethernet.c"]
    objects = []
    for item in sources:
        target = output / (item.relative_to(source).as_posix().replace("/", "_") + ".o")
        run([cc, "-std=c11", *common, "-c", str(item), "-o", str(target)])
        objects.append(str(target))
    binary = output / "net_service_host"
    strict = ["-Wall", "-Wextra", "-Werror"]
    run([cxx, "-std=c++20", *strict, *common, str(fixture),
         *map(str, production_sources), *objects, "-o", str(binary)])
    loop_binary = output / "net_service_loop_host"
    run([cxx, "-std=c++20", *strict, *common, "-I", str(root / "src/user/include"),
         str(loop_fixture), str(root / "src/user/network/service_loop.cpp"),
         *map(str, production_sources), *objects, "-o", str(loop_binary)])
    freestanding = ["-std=c++20", "-O2", *strict, "-ffreestanding", "-fno-exceptions",
                    "-fno-rtti", "-nostdinc++", "-mno-red-zone", *includes,
                    "-I", str(root / "src/user/include")]
    for item, label, flags in compile_inputs:
        run([cxx, *freestanding, *flags, "-c", str(item), "-o", str(output / (label + ".o"))])
    scenarios = subprocess.check_output([str(binary), "--list"], text=True).splitlines()
    loop_scenarios = subprocess.check_output([str(loop_binary), "--list"], text=True).splitlines()
    for scenario in scenarios:
        run([str(binary), scenario])
    for scenario in loop_scenarios:
        run([str(loop_binary), scenario])
    for name, expected in input_hashes.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Network input changed while the test ran: {name}; rerun required")
    receipt = {"guest_qualification": "not_run", "wire_version": 2,
               "lwip_archive_sha256": lock["sha256"], "scenarios": scenarios,
               "lwip_patches": lock.get("patches", []),
               "loop_scenarios": loop_scenarios,
               "sanitizers": ["address", "undefined"] if options.sanitize else [],
               "asan_options": os.environ.get("ASAN_OPTIONS", ""),
               "inputs": input_hashes}
    (output / "result.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"NET_SERVICE_REAL_LWIP_SCENARIOS_PASSED={len(scenarios)}")
    print(f"NET_SERVICE_PRODUCTION_LOOP_SCENARIOS_PASSED={len(loop_scenarios)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", default=os.environ.get("XOS_LWIP_SOURCE_ARCHIVE"))
    parser.add_argument("--output", type=Path, help="preserve isolated build output and receipt")
    parser.add_argument("--sanitize", action="store_true")
    options = parser.parse_args()
    if not options.archive:
        parser.error("--archive or XOS_LWIP_SOURCE_ARCHIVE is required; no test was run")
    if options.output:
        build_and_test(options, options.output.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="xos_net_service_") as temporary:
            build_and_test(options, Path(temporary))


if __name__ == "__main__":
    main()
