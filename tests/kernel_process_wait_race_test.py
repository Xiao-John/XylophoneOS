# SPDX-License-Identifier: Apache-2.0
"""Compile the real process-wait/finish/delivery code in a host harness.

The selected definitions are extracted unchanged from tasks.cpp, including its
process/thread records. Only privileged page-table lookup, scheduling, and the
unrelated device/service teardown hooks are replaced by the harness. This is a
deterministic host regression, not guest or hardware qualification.
"""
import argparse
import hashlib
import json
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
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    source_bytes = args.source.read_bytes()
    source = source_bytes.decode('utf-8')
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
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
        "bool process_completion_claimed(u64 parent, u64 pid) {",
        "completion_record* next_process_completion(u64 parent, bool& has_children) {",
        "void wake_process_waiters(u64 parent) {",
        "void finish_task(process_record* task, process_outcome outcome, i64 code,\n"
        "                  u64 vector, u64 address, u64 instruction) {",
        "void deliver_wait(thread_record* thread, interrupt_frame* frame) {",
        "process_record* owned_process(u64 handle) {",
    )
    implementation = "\n".join(definition(source, value) for value in signatures if value in source)
    ipc_copy = "void copy_ipc_payload(void* destination, const void* source, u32 length) {"
    if ipc_copy in source:
        implementation = definition(source, ipc_copy) + implementation
    runtime_vm = "user_copyout output;" in source
    if runtime_vm:
        implementation = definition(source, "void commit_user_output() {") + implementation
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
        directory = args.output.resolve() if args.output else Path(temporary)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "kernel_wait_records.inc").write_text(records)
        (directory / "kernel_wait_implementation.inc").write_text(implementation + dispatch)
        binary = directory / "kernel_process_wait_race_test"
        command = [
            os.environ.get("CXX", "c++"), "-std=c++20", "-Wall", "-Wextra", "-Werror",
            "-DXOS_COW1_PROBE=0", "-I", str(directory), "-I", str(repo_root / "src/kernel"),
            "-DXOS_RUNTIME_VM=" + str(int(runtime_vm)),
            "-DXOS_PROCESS_WAIT_ANY=" + str(int("bool published;" in source)),
            "-I", str(repo_root / "src/kernel/include"), "-I", str(repo_root / "src/shared/include"),
            str(repo_root / "tests/kernel_process_wait_race_test.cpp"), "-o", str(binary),
        ]
        if args.sanitize:
            command[1:1] = ["-O1", "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                            "-fno-omit-frame-pointer"]
        environment = os.environ.copy()
        if args.sanitize:
            environment['ASAN_OPTIONS'] = 'detect_leaks=0:abort_on_error=1'
            environment['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
        report = {'status': 'failed', 'scope': 'production tasks.cpp wait/finish/deferred delivery extraction',
                  'command': command, 'source_sha256': source_sha256,
                  'sanitizers': ['address', 'undefined'] if args.sanitize else [],
                  'guest': 'not_run', 'leak_sanitizer': 'not_run', 'results': []}
        inputs = [repo_root / 'tests/kernel_process_wait_race_test.cpp', Path(__file__).resolve()]
        inputs += list((repo_root / 'src/kernel/core').rglob('*.hpp'))
        inputs += list((repo_root / 'src/kernel/include').rglob('*.hpp'))
        inputs += list((repo_root / 'src/shared/include').rglob('*.hpp'))
        report['inputs'] = {str(path.relative_to(repo_root)): hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in sorted(set(inputs))}
        try:
            with (directory / 'compile.log').open('w') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
            run = subprocess.run([str(binary)], text=True, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, env=environment)
            (directory / 'host.log').write_text(run.stdout)
            print(run.stdout, end='')
            report['returncode'] = run.returncode
            report['results'] = [line for line in run.stdout.splitlines() if line.startswith('PASS ')]
            if run.returncode != 0:
                raise RuntimeError('production wait host fixture failed')
            report['status'] = 'pass'
        except BaseException as error:
            report['error'] = str(error)
            raise
        finally:
            (directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == "__main__":
    main()
