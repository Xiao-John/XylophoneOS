# SPDX-License-Identifier: Apache-2.0
"""Inventory the current SDK's libc references and XOS definitions."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "build/sdk"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def symbols(*args, nm="x86_64-elf-nm"):
    output = subprocess.check_output([nm, *args], text=True)
    values = []
    for line in output.splitlines():
        fields = line.split()
        # Archive member headings are not symbols.
        if len(fields) >= 2 and len(fields[-2]) == 1:
            values.append(fields[-1])
    return values


def main():
    libc = SDK / "lib/libc.a"
    libm = SDK / "lib/libm.a"
    if not libc.is_file() or not libm.is_file():
        raise SystemExit("Run make build first")
    unresolved = sorted(set(symbols("-u", str(libc))))
    definitions = set(symbols("--defined-only", "-g", str(SDK / "lib/libxos.a"),
                              str(SDK / "lib/libxos_loader.a")))
    provided = sorted(set(unresolved) & definitions)
    metadata = json.loads((SDK / "manifest.json").read_text())
    hello = SDK.parent / "user_libc_hello.image.elf"
    report = {
        "newlib_version": metadata["libc"]["version"],
        "build_id": metadata["build_id"],
        "configuration": {
            "target": metadata["target"],
            "runtime_model": metadata["runtime_model"],
            "libc_sha256": sha256(libc),
            "libm_sha256": sha256(libm),
            "libc_bytes": libc.stat().st_size,
            "libm_bytes": libm.stat().st_size,
        },
        "provided_syscall_symbols": provided,
        "defined_path_syscall_symbols": sorted(definitions & {"open", "stat", "unlink"}),
        "unresolved_symbol_count": len(unresolved),
        "libc_hello": {
            "bytes": hello.stat().st_size if hello.is_file() else None,
            "sha256": sha256(hello) if hello.is_file() else None,
        },
        "notes": [
            "Undefined references are counted across libc archive members before final linking; "
            "some are resolved by other members of libc itself.",
            "Provided symbols are measured from libxos.a and libxos_loader.a, not a historical allowlist.",
            "Symbol presence does not establish runtime semantics or guest qualification; "
            "use the file, libc, threading and process regression suites.",
        ],
    }
    (ROOT / "build/libc_audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
