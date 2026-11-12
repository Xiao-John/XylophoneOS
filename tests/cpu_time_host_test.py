# SPDX-License-Identifier: Apache-2.0
"""Compile real accounting and libc clock bridges; syscall transport is injected.

The libc translation unit uses the repository's actual newlib headers. Extracted
functions are unchanged; preprocessor names keep their exported symbols from
overriding the host libc during the test. No guest or TSC calibration claim.
"""
import os
from pathlib import Path
import subprocess
import tempfile

from kernel_process_wait_race_test import definition

repo_root = Path(__file__).resolve().parents[1]


def main():
    source = (repo_root / "src/user/libc/newlib_syscalls.cpp").read_text()
    functions = "\n".join(definition(source, signature) for signature in (
        'extern "C" clock_t _times(struct tms* result) {',
        'extern "C" clock_t times(struct tms* result) {',
        'extern "C" clock_t clock() {',
    ))
    pthread = (repo_root / "src/user/threading/pthread.cpp").read_text()
    clock_functions = "\n".join(definition(pthread, signature) for signature in (
        'extern "C" int clock_gettime(clockid_t clock, timespec* value) {',
        'extern "C" int clock_getres(clockid_t clock, timespec* value) {',
    ))
    with tempfile.TemporaryDirectory(prefix="xos_cpu_time_") as temporary:
        directory = Path(temporary)
        (directory / "cpu_libc.inc").write_text(functions)
        (directory / "cpu_pthread.inc").write_text(clock_functions)
        cxx = os.environ.get("CXX", "c++")
        common = [cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror"]
        core = directory / "cpu_accounting"
        subprocess.run(common + ["-I", str(repo_root / "src/kernel"),
            "-I", str(repo_root / "src/kernel/include"),
            "-I", str(repo_root / "src/shared/include"),
            str(repo_root / "tests/cpu_accounting_host_test.cpp"), "-o", str(core)], check=True)
        subprocess.run([str(core)], check=True)
        binary = directory / "cpu_libc"
        subprocess.run(common + ["-I", str(directory),
            "-I", str(repo_root / "src/user/include"),
            "-I", str(repo_root / "src/user/threading/include"),
            "-I", str(repo_root / "src/shared/include"),
            "-isystem", str(repo_root / "src/third_party/newlib/x86_64-elf/include"),
            str(repo_root / "tests/cpu_time_libc_host_test.cpp"), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
