"""Produce the E06 dependency audit from the actual vendored SDK artifacts."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "build/sdk"
NEWLIB = ROOT / "src/third_party/newlib/x86_64-elf"
PROVIDED = {
    "_write", "_read", "_close", "_sbrk", "_fstat", "_isatty", "_lseek",
    "_exit", "_getpid", "_kill", "_times", "write", "read", "close", "sbrk",
    "fstat", "isatty", "lseek", "getpid", "kill", "open", "stat", "unlink",
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def symbols(*args):
    output = subprocess.check_output(["x86_64-elf-nm", *args], text=True)
    values = []
    for line in output.splitlines():
        fields = line.split()
        if fields:
            values.append(fields[-1])
    return values


def main():
    libc = SDK / "lib/libc.a"
    libm = SDK / "lib/libm.a"
    if not libc.is_file() or not libm.is_file():
        raise SystemExit("Run make build first")
    unresolved = sorted(set(symbols("-u", str(libc))))
    provided = sorted(s for s in unresolved if s in PROVIDED)
    unsupported = [s for s in ("open", "stat", "unlink") if s in provided]
    hello = SDK.parent / "user_libc_hello.image.elf"
    report = {
        "newlib_version": "4.6.0.20260123",
        "configuration": {
            "target": "x86_64-elf",
            "libc_sha256": sha256(libc),
            "libm_sha256": sha256(libm),
            "libc_bytes": libc.stat().st_size,
            "libm_bytes": libm.stat().st_size,
            "sse": True,
            "multilib": False,
            "newlib_supplied_syscalls": False,
            "lfn": False,
        },
        "provided_syscall_symbols": provided,
        "unsupported_path_syscalls": unsupported,
        "unresolved_symbol_count": len(unresolved),
        "libc_hello": {
            "bytes": hello.stat().st_size if hello.is_file() else None,
            "sha256": sha256(hello) if hello.is_file() else None,
        },
        "notes": [
            "console read/write and a 64 KiB static sbrk heap are implemented",
            "open/stat/unlink return ENOSYS; POSIX file paths are not mapped to the XOS file service",
            "per-task FXSAVE/FXRSTOR supplies SSE/x87 state; no libstdc++/exceptions/TLS",
        ],
    }
    (ROOT / "build/libc_audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
