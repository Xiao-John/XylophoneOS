# SPDX-License-Identifier: Apache-2.0
"""Run the real allocator, page tables and copyout transaction without ring 0.

Only CR3 reads and TLB instructions are replaced. The real allocator owns a
fixed host mapping for its physical identity window; all COW/fork/protection/
reference-count algorithms are compiled unchanged from the kernel sources.
This does not qualify interrupt entry, hardware TLBs, or a guest boot.
"""
import os
from pathlib import Path
import subprocess
import tempfile

repo_root = Path(__file__).resolve().parents[1]


def replace_definition(source, signature, replacement):
    start = source.index(signature)
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[:start] + replacement + source[end:]


def main():
    source = (repo_root / "src/kernel/arch/x86_64/paging.cpp").read_text()
    replacements = (
        ("u64 read_cr3() {", "u64 read_cr3() { return host_active_cr3; }"),
        ("void flush_tlb() {", "void flush_tlb() {}"),
        ("void invalidate(u64 virtual_address) {",
         "void invalidate(u64 virtual_address) { (void)virtual_address; ++host_invalidations; }"),
    )
    for signature, replacement in replacements:
        source = replace_definition(source, signature, replacement)
    source = "#include <xos/types.hpp>\nextern xos::u64 host_active_cr3, host_invalidations;\n" + source
    with tempfile.TemporaryDirectory(prefix="xos_cow_runtime_") as temporary:
        directory = Path(temporary)
        (directory / "paging_host.cpp").write_text(source)
        (directory / "build_info.hpp").write_text("#pragma once\n")
        binary = directory / "cow_runtime_host_test"
        subprocess.run([
            os.environ.get("CXX", "c++"), "-std=c++20", "-Wall", "-Wextra", "-Werror",
            "-I", str(directory), "-I", str(repo_root / "src/kernel/arch/x86_64"),
            "-I", str(repo_root / "src/kernel"), "-I", str(repo_root / "src/kernel/include"),
            "-I", str(repo_root / "src/shared/include"),
            str(directory / "paging_host.cpp"), str(repo_root / "src/kernel/core/memory.cpp"),
            str(repo_root / "tests/cow_runtime_host_test.cpp"), "-o", str(binary),
        ], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
