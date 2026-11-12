# SPDX-License-Identifier: Apache-2.0
"""Compile the real process-wait/finish/delivery code in a host harness.

The selected definitions are extracted unchanged from tasks.cpp, including its
process/thread records. Only privileged page-table lookup, scheduling, and the
unrelated device/service teardown hooks are replaced by the harness. This is a
deterministic host regression, not guest or hardware qualification.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

repo_root = Path(__file__).resolve().parents[1]


def definition(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
        end += 1
    return source[start:end] + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
                        default=repo_root / "src/kernel/arch/x86_64/tasks.cpp")
    args = parser.parse_args()
    source = args.source.read_text()
    records = source[source.index("constexpr u64 user_base"):
                     source.index("enum class ipc_v1_call_state")]
    signatures = (
        "void copy_bytes(void* destination, const void* source, u64 length) {",
        "void copy_from_user(void* destination, u64 source, u64 length) {",
        "void copy_to_user(u64 destination, const void* source, u64 length) {",
        "bool user_range_ok(u64 address, u64 length, bool write) {",
        "u32 task_index(process_record* task) {",
        "void mark_reap(process_record* task) {",
        "completion_record* completion_for(u64 parent, u64 pid) {",
        "void finish_task(process_record* task, process_outcome outcome, i64 code,\n"
        "                  u64 vector, u64 address, u64 instruction) {",
        "void deliver_wait(thread_record* thread, interrupt_frame* frame) {",
        "process_record* owned_process(u64 handle) {",
    )
    implementation = "\n".join(definition(source, value) for value in signatures)
    wait_case = definition(source, "case sys_process_wait: {")
    dispatch = """
void* wait_syscall(interrupt_frame* frame) {
    i64 result = process_error_invalid;
    const u64 first = frame->rdi, second = frame->rsi, third = frame->rdx;
    switch (frame->rax) {
""" + wait_case + """
    }
    frame->rax = static_cast<u64>(result);
    return frame;
}
"""
    with tempfile.TemporaryDirectory(prefix="xos_kernel_wait_") as temporary:
        directory = Path(temporary)
        (directory / "kernel_wait_records.inc").write_text(records)
        (directory / "kernel_wait_implementation.inc").write_text(implementation + dispatch)
        binary = directory / "kernel_process_wait_race_test"
        subprocess.run([
            os.environ.get("CXX", "c++"), "-std=c++20", "-Wall", "-Wextra", "-Werror",
            "-DXOS_COW1_PROBE=0", "-I", str(directory), "-I", str(repo_root / "src/kernel"),
            "-I", str(repo_root / "src/kernel/include"), "-I", str(repo_root / "src/shared/include"),
            str(repo_root / "tests/kernel_process_wait_race_test.cpp"), "-o", str(binary),
        ], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
