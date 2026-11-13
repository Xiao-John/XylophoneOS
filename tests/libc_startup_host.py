# SPDX-License-Identifier: Apache-2.0
"""Run production libc startup and execvp against a host IPC boundary fixture."""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "tests"))
from host_tools import IS_DARWIN, gc_sections_flags, nm_defined_args, nm_program, objcopy_program


def main():
    compiler = shutil.which("c++")
    nm = nm_program()
    objcopy = objcopy_program()
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
        symbols = subprocess.check_output([nm, *nm_defined_args(), str(runtime)], text=True)
        mapping = output / "symbols.txt"
        renamed = []
        for line in symbols.splitlines():
            name = line.split()[0]
            prefix = "_" if IS_DARWIN and name.startswith("_") else ""
            base = name[len(prefix):]
            if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", base) and not base.startswith("_Z"):
                renamed.append(f"{name} {prefix}audit_{base}\n")
        mapping.write_text("".join(renamed))
        subprocess.run([objcopy, "--redefine-syms=" + str(mapping), str(runtime)], check=True)
        binary = output / "libc_startup"
        subprocess.run([compiler, *flags, str(repo_root / "tests/libc_startup_host_test.cpp"),
                        str(repo_root / "src/user/sdk/file_client.cpp"),
                        str(repo_root / "src/user/sdk/terminal_client.cpp"),
                        str(repo_root / "src/user/sdk/text.cpp"),
                        str(repo_root / "src/user/loader/load.cpp"),
                        str(repo_root / "src/user/loader/elf.cpp"),
                        str(repo_root / "src/user/arch/x86_64/tls.cpp"), str(runtime),
                        *gc_sections_flags(), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
