# SPDX-License-Identifier: Apache-2.0
"""Exercise the production sys90 authorization and snapshot code on the host.

Task/endpoint/thread records, the observation implementation, and its syscall
case are extracted unchanged from tasks.cpp. Only the monotonic clock and user
copy boundary are host substitutes. This does not claim guest qualification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def definition(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    source_path = ROOT / "src/kernel/arch/x86_64/tasks.cpp"
    source = source_path.read_text()
    constants = "\n".join(re.search(r"constexpr u32 " + name + r" = [^;]+;", source).group()
                          for name in ("max_endpoints", "file_message_bytes")) + "\n"
    records = constants + "\n".join(definition(source, name).rstrip() + ";"
        for name in ("enum class task_state", "struct stdio_route", "struct pipe_reference",
                     "struct process_record", "struct endpoint_record", "struct ipc_name_record",
                     "struct thread_record"))
    functions = "\n".join(definition(source, signature) for signature in (
        "char state_label(const process_record& task) {",
        "endpoint_record* endpoint_for(u64 handle) {", "process_record* task_by_pid(u64 pid) {",
        "bool ipc_service_published(u64 pid) {",
        "observe_native::result observe_snapshot(const observe_native::request& request,"))
    dispatch = """
i64 observe_call(interrupt_frame& frame) {
    i64 result = static_cast<i64>(observe_native::result::invalid);
    switch (frame.rax) {
""" + definition(source, "case sys_observe: {").replace("frame->", "frame.") + """
    }
    return result;
}
"""
    with tempfile.TemporaryDirectory(prefix="xos_observation_native_") as temporary:
        directory = args.output.resolve() if args.output else Path(temporary)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "observation_records.inc").write_text(records)
        (directory / "observation_implementation.inc").write_text(functions + dispatch)
        binary = directory / "observation_native_host"
        command = [os.environ.get("CXX", "c++"), "-std=c++20", "-Wall", "-Wextra", "-Werror",
                   "-DXOS_COW1_PROBE=0", "-I", str(directory), "-I", str(ROOT / "src/kernel"),
                   "-I", str(ROOT / "src/kernel/include"), "-I", str(ROOT / "src/shared/include"),
                   str(ROOT / "tests/fixtures/observation_native_host.cpp"), "-o", str(binary)]
        if args.sanitize:
            command[1:1] = ["-O1", "-g", "-fsanitize=address,undefined",
                            "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
        report = {"status": "failed", "scope": "extracted production sys90",
                  "guest": "not_run", "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                  "sanitizers": ["address", "undefined"] if args.sanitize else []}
        try:
            compiled = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT)
            (directory / "compile.log").write_text(compiled.stdout)
            if compiled.returncode:
                print(compiled.stdout, end="")
                raise RuntimeError("observation native host compilation failed")
            env = os.environ.copy()
            env["ASAN_OPTIONS"] = "detect_leaks=0:abort_on_error=1"
            run = subprocess.run([str(binary)], text=True, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, env=env)
            (directory / "host.log").write_text(run.stdout)
            print(run.stdout, end="")
            report["returncode"] = run.returncode
            report["results"] = run.stdout.splitlines()
            if run.returncode:
                raise RuntimeError("observation native host fixture failed")
            report["status"] = "passed"
        finally:
            (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
