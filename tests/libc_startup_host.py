# SPDX-License-Identifier: Apache-2.0
"""Run production libc startup and execvp against a host IPC boundary fixture."""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

repo_root = Path(__file__).resolve().parents[1]
# GNU ld drops unreachable sections with --gc-sections; Apple's ld uses dead_strip.
GC_SECTIONS = ["-Wl,-dead_strip"] if sys.platform == "darwin" else ["-Wl,--gc-sections"]


def main():
    compiler = shutil.which("c++")
    with tempfile.TemporaryDirectory(prefix="xos_libc_startup_") as temporary:
        output = Path(temporary)
        flags = ["-std=c++20", "-ffreestanding", "-fno-builtin", "-fno-exceptions",
                 "-ffunction-sections", "-fdata-sections",
                 "-I" + str(repo_root / "src/user/include"),
                 "-I" + str(repo_root / "src/shared/include"),
                 "-I" + str(repo_root / "src/third_party/newlib/x86_64-elf/include")]
        runtime = output / "runtime.o"
        subprocess.run([compiler, *flags, "-c", str(repo_root / "src/user/libc/newlib_syscalls.cpp"),
                        "-o", str(runtime)], check=True)
        symbols = subprocess.check_output(["nm", "-P", "-g", "--defined-only", str(runtime)], text=True)
        mapping = output / "symbols.txt"
        mapping.write_text("".join(f"{name} audit_{name}\n" for line in symbols.splitlines()
                                  if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name := line.split()[0])
                                  and not name.startswith("_Z")))
        subprocess.run(["objcopy", "--redefine-syms=" + str(mapping), str(runtime)], check=True)
        binary = output / "libc_startup"
        subprocess.run([compiler, *flags, str(repo_root / "tests/libc_startup_host_test.cpp"),
                        str(repo_root / "src/user/sdk/file_client.cpp"),
                        str(repo_root / "src/user/sdk/terminal_client.cpp"),
                        str(repo_root / "src/user/sdk/text.cpp"),
                        str(repo_root / "src/user/loader/load.cpp"),
                        str(repo_root / "src/user/loader/elf.cpp"),
                        str(repo_root / "src/user/arch/x86_64/tls.cpp"), str(runtime),
                        *GC_SECTIONS, "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
