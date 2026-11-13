# SPDX-License-Identifier: Apache-2.0
"""Real file service/FatFs and libc/SDK integration over a private memory disk."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "scripts"))
from make_work_disk import make_image


def main():
    compiler = shutil.which("c++")
    output = repo_root / "build/file_identity"
    output.mkdir(parents=True, exist_ok=True)
    includes = ["-I" + str(repo_root / path) for path in (
        "src/user/include", "src/shared/include", "src/third_party/fatfs")]
    host_flags = [compiler, "-std=c++20", "-O1", "-ffunction-sections", "-fdata-sections", *includes]
    runtime_flags = [*host_flags, "-ffreestanding", "-fno-builtin", "-fno-exceptions",
                     "-I" + str(repo_root / "src/third_party/newlib/x86_64-elf/include")]
    commands = []
    logs = []

    def run(command):
        commands.append([str(part) for part in command])
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        if result.stdout:
            logs.append(result.stdout)
            print(result.stdout, end="")
        return result

    with tempfile.TemporaryDirectory(prefix="xos_file_identity_") as temporary:
        image = Path(temporary) / "private.img"
        image.write_bytes(make_image())
        fatfs = output / "fatfs.o"
        unicode = output / "fatfs_unicode.o"
        run([*host_flags, "-w", "-c", repo_root / "src/third_party/fatfs/ff.c", "-o", fatfs])
        run([*host_flags, "-c", repo_root / "src/user/services/fatfs_unicode.cpp", "-o", unicode])
        service_test = output / "file_identity"
        run([*host_flags, repo_root / "tests/fixtures/file_semantics/file_identity.cpp", fatfs,
             unicode, "-Wl,--gc-sections", "-o", service_test])
        run([service_test, image])

        runtime = output / "runtime.o"
        run([*runtime_flags, "-c", repo_root / "src/user/libc/newlib_syscalls.cpp", "-o", runtime])
        symbols = subprocess.check_output(["nm", "-P", "-g", "--defined-only", runtime], text=True)
        mapping = output / "symbols.txt"
        mapping.write_text("".join(f"{name} audit_{name}\n" for line in symbols.splitlines()
                                  if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name := line.split()[0])
                                  and not name.startswith("_Z")))
        run([os.environ.get("OBJCOPY", "objcopy"), "--redefine-syms=" + str(mapping), runtime])
        service = output / "service.o"
        run([*host_flags, "-c", repo_root / "tests/fixtures/file_semantics/libc_service.cpp", "-o", service])
        libc_test = output / "libc_identity"
        sources = [repo_root / path for path in (
            "tests/fixtures/file_semantics/libc_identity.cpp", "src/user/sdk/file_client.cpp",
            "src/user/sdk/terminal_client.cpp", "src/user/sdk/text.cpp")]
        run([*runtime_flags, *sources, runtime, service, fatfs, unicode,
             "-Wl,--gc-sections", "-o", libc_test])
        run([libc_test, image])

    paths = ["src/user/services/files.cpp", "src/user/libc/newlib_syscalls.cpp",
             "src/user/sdk/file_client.cpp", "src/shared/include/xos/file_abi.hpp",
             "src/third_party/fatfs/ff.c", "src/third_party/fatfs/ff.h"]
    paths.extend(str(path.relative_to(repo_root)) for path in
                 sorted((repo_root / "tests/fixtures/file_semantics").glob("*.cpp")))
    report = {"status": "passed", "guest": "not_run_by_this_host_runner",
              "scope": "production libc/SDK/file service/FatFs; simulated kernel IPC transport",
              "commands": commands, "output": "".join(logs),
              "sources": {path: hashlib.sha256((repo_root / path).read_bytes()).hexdigest() for path in paths}}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
