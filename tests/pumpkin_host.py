# SPDX-License-Identifier: Apache-2.0
"""Exercise Pumpkin's production identity and session core on the host."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile


root = Path(__file__).resolve().parents[1]
module = root / "src/user/pumpkin"
core_sources = [module / name for name in ("account_store.cpp", "service_core.cpp")]
protocol_source = module / "daemon_protocol.cpp"
publication_source = module / "snapshot_publication.cpp"
resource_source = module / "resource_dispatch.cpp"
fixtures = [
    ("pumpkin_core_host", "service_core_host.cpp", [*core_sources, protocol_source, resource_source]),
    ("pumpkin_publication_host", "snapshot_publication_host.cpp", [*core_sources, publication_source]),
]
common = ["-std=c++20", "-Wall", "-Wextra", "-Werror",
          "-I", str(root / "src/shared/include"), "-I", str(root / "src/user/include"),
          "-I", str(root / "src/user")]


def run(options, output):
    output.mkdir(parents=True, exist_ok=True)
    optimization = ["-O2"]
    if options.sanitize:
        optimization = ["-O1", "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                        "-fno-omit-frame-pointer"]
    for program, fixture, program_sources in fixtures:
        executable = output / program
        subprocess.run([options.cxx, *common, *optimization, *program_sources,
                        root / "tests/fixtures/pumpkin" / fixture, "-o", executable],
                       check=True, timeout=60)
        subprocess.run([executable], check=True, timeout=30)
    if options.target_cxx:
        target = ["-O2", "-ffreestanding", "-fno-exceptions", "-fno-rtti", "-nostdinc++",
                  "-mno-red-zone", "-fstack-usage"]
        for source in [*core_sources, protocol_source, publication_source, resource_source]:
            subprocess.run([options.target_cxx, *common, *target, "-c", source,
                            "-o", output / (source.stem + ".o")], check=True, timeout=60)
        print("PASS freestanding x86-64 object compilation", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default=os.environ.get("CXX", "c++"))
    parser.add_argument("--target-cxx", help="also compile the core with an x86-64 XOS cross compiler")
    parser.add_argument("--sanitize", action="store_true")
    parser.add_argument("--output", type=Path)
    options = parser.parse_args()
    if options.output:
        run(options, options.output.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="pumpkin_host_") as directory:
            run(options, Path(directory))


if __name__ == "__main__":
    main()
