# SPDX-License-Identifier: Apache-2.0
"""Exercise real kernel copyout consumers against real COW page tables.

CR3/TLB operations map a private host memfd into the selected user VA. The real
allocator, page tables, output transaction, syscall error translation and read
consumers are unchanged. Device input and unrelated wake hooks are test ports.
"""
import os
from pathlib import Path
import subprocess
import tempfile

from cow_runtime_host_test import replace_definition
from kernel_process_wait_race_test import definition

repo_root = Path(__file__).resolve().parents[1]


def main():
    tasks = (repo_root / "src/kernel/arch/x86_64/tasks.cpp").read_text()
    records = tasks[tasks.index("constexpr u64 user_base"):tasks.index("enum class ipc_v1_call_state")]
    signatures = (
        "void copy_bytes(void* destination, const void* source, u64 length) {",
        "void copy_from_user(void* destination, u64 source, u64 length) {",
        "void commit_user_output() {",
        "void copy_to_user(u64 destination, const void* source, u64 length) {",
        "bool user_range_ok(u64 address, u64 length, bool write) {",
        "bool rdrand_supported() {", "bool rdrand_word(u64& value) {",
        "i64 random_bytes(u64 destination, u64 length) {",
        "endpoint_record* endpoint_for(u64 handle) {",
        "i64 ipc_recv(u64 handle, u64 address, u64 length) {",
        "i64 pipe_read_from(u32 pipe_index, u64 address, u64 length) {",
        "i64 stdio_read(process_record* task, u32 fd, u64 address, u64 length,\n"
        "               bool console_empty_is_error) {",
        "void* syscall_entry(interrupt_frame* frame) {",
    )
    implementation = "\n".join(definition(tasks, signature) for signature in signatures)
    device = (repo_root / "src/kernel/arch/x86_64/device_tasks.inc").read_text()
    implementation += definition(device, "union device_input_snapshot {") + ";\n"
    implementation += definition(device, "i64 read_device_request(interrupt_frame* frame, device_request& request, device_input_snapshot& input) {")
    implementation += definition(device, "void* device_authorize_syscall(interrupt_frame* frame) {")
    paging = (repo_root / "src/kernel/arch/x86_64/paging.cpp").read_text()
    for signature, replacement in (
        ("u64 read_cr3() {", "u64 read_cr3() { return host_active_cr3; }"),
        ("void flush_tlb() {", "void flush_tlb() {}"),
        ("void invalidate(u64 virtual_address) {", "void invalidate(u64 virtual_address) { host_invalidate(virtual_address); }"),
    ):
        paging = replace_definition(paging, signature, replacement)
    paging = "#include <xos/types.hpp>\nextern xos::u64 host_active_cr3;\nvoid host_invalidate(xos::u64);\n" + paging
    with tempfile.TemporaryDirectory(prefix="xos_kernel_copyout_") as temporary:
        directory = Path(temporary)
        (directory / "kernel_copyout_records.inc").write_text(records)
        (directory / "kernel_copyout_implementation.inc").write_text(implementation)
        (directory / "paging_host.cpp").write_text(paging)
        (directory / "build_info.hpp").write_text("#pragma once\n")
        binary = directory / "kernel_copyout"
        subprocess.run([os.environ.get("CXX", "c++"), "-std=c++20", "-Wall", "-Wextra", "-Werror",
            "-DXOS_COW1_PROBE=0", "-I", str(directory),
            "-I", str(repo_root / "src/kernel/arch/x86_64"), "-I", str(repo_root / "src/kernel"),
            "-I", str(repo_root / "src/kernel/include"), "-I", str(repo_root / "src/shared/include"),
            str(directory / "paging_host.cpp"), str(repo_root / "src/kernel/core/memory.cpp"),
            str(repo_root / "tests/kernel_copyout_host_test.cpp"), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
