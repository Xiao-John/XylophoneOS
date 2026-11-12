# SPDX-License-Identifier: Apache-2.0
"""Run real grant close preflight and fork admission against real reservations.

Definitions and records are extracted unchanged from tasks.cpp. No page tables
are changed: the files-service boundary deliberately stops admitted fork calls
before allocation. This covers both eager and COW admission, not guest runtime.
"""
import os
from pathlib import Path
import subprocess
import tempfile

from kernel_process_wait_race_test import definition

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = (ROOT / "src/kernel/arch/x86_64/tasks.cpp").read_text()
    records = source[source.index("constexpr u64 user_base"):
                     source.index("enum class ipc_v1_call_state")]
    for name in ("ipc_v1_grant_handle_record", "ipc_v1_grant_mapping_record", "fork_copy_transaction"):
        records += definition(source, "struct " + name + " {") + ";\n"
    start = source.index("constexpr i64 fork_async_result =")
    records += source[start:source.index(";", start) + 1] + "\n"
    implementation = "\n".join(definition(source, signature) for signature in (
        "thread_record& main_thread(process_record* process) {",
        "process_record* task_by_pid(u64 pid) {",
        "bool pinned_range(process_record* process, u64 begin, u64 end) {",
        "i64 ipc_v1_grant_close_status(u32 slot) {",
        "i64 prepare_fork(interrupt_frame* frame) {",
    ))
    with tempfile.TemporaryDirectory(prefix="xos_grant_lifecycle_") as temporary:
        directory = Path(temporary)
        (directory / "grant_records.inc").write_text(records)
        (directory / "grant_implementation.inc").write_text(implementation)
        for cow in (0, 1):
            binary = directory / f"grant_lifecycle_{cow}"
            subprocess.run([os.environ.get("CXX", "c++"), "-std=c++20", "-O2", "-Wall", "-Wextra",
                            "-Werror", "-Wconversion", "-Wshadow", "-DXOS_COW1_PROBE=0",
                            "-DXOS_VM1_PROBE=0", f"-DXOS_COW_FORK={cow}",
                            "-I", str(directory), "-I", str(ROOT / "src/kernel"),
                            "-I", str(ROOT / "src/kernel/include"), "-I", str(ROOT / "src/shared/include"),
                            str(ROOT / "tests/fixtures/ipc_v1_grant/grant_lifecycle_host.cpp"),
                            "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
