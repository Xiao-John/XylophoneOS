# SPDX-License-Identifier: Apache-2.0
"""Run the production provisioning codec/store/RPC transaction and authority cases."""
import argparse
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]


def run(output, cxx, sanitize):
    output.mkdir(parents=True, exist_ok=True)
    sources = [root / "src/user/pumpkin" / name for name in (
        "account_store.cpp", "service_core.cpp", "snapshot_publication.cpp", "provisioning_store.cpp", "provisioning_protocol.cpp")]
    flags = ["-std=c++20", "-Wall", "-Wextra", "-Werror", "-DXOS_PUMPKIN_PROVISIONING_STORE=1",
             "-I", str(root / "src/shared/include"), "-I", str(root / "src/user/include"), "-I", str(root / "src/user")]
    flags += ["-O1", "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=all"] if sanitize else ["-O2"]
    program = output / "provisioning_host"
    subprocess.run([cxx, *flags, *sources, root / "tests/fixtures/pumpkin/provisioning_store_host.cpp", "-o", program], check=True)
    subprocess.run([program], check=True, timeout=30)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cxx", default="c++")
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    if args.output:
        run(args.output, args.cxx, args.sanitize)
    else:
        with tempfile.TemporaryDirectory(prefix="pumpkin_provisioning_") as directory:
            run(Path(directory), args.cxx, args.sanitize)
