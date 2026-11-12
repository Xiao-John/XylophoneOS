# SPDX-License-Identifier: Apache-2.0
"""Run the real SSG pipe transfer functions with a scheduled syscall transport.

No Qt implementation is substituted: only the Qt-independent transport methods,
wire encoder and subscriber I/O functions are extracted unchanged. The scripted
transport makes readiness arrive before or after the absolute deadline.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

from kernel_process_wait_race_test import definition

repo_root = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", help="Read the implementation from this repository's Git history")
    args = parser.parse_args()

    def read(relative):
        if args.revision:
            return subprocess.check_output(
                ["git", "show", f"{args.revision}:{relative}"], cwd=repo_root, text=True)
        return (repo_root / relative).read_text()

    sink = read("src/user/ssg/pipe_event_sink.hpp")
    subscriber = read("src/user/apps/ssg_subscriber.cpp")
    wire = read("src/user/ssg/subscription_wire.hpp")
    pieces = [
        "struct actual_sink {\n xos::u32 event_write_=100,ack_read_=101;\n",
        definition(sink, "    enum class io_state") + ";\n",
        definition(sink, "    io_state write_frame("),
        definition(sink, "    io_state read_exact("),
        "};\n",
        wire[wire.index("namespace ssg_subscription {"):wire.index("// Test-build audit only.")],
        definition(wire, "inline bool encode_ack("),
        "}\nnamespace actual_subscriber {\nusing namespace xos;\nusing namespace ssg_subscription;\n",
        subscriber[subscriber.index("constexpr u64 frame_timeout_ns="):subscriber.index("enum class read_state")],
        definition(subscriber, "enum class read_state") + ";\n",
        definition(subscriber, "template<class... Args>\nvoid log_line("),
        definition(subscriber, "read_state read_exact("),
        definition(subscriber, "bool write_ack("),
        "}\n",
    ]
    with tempfile.TemporaryDirectory(prefix="xos_ssg_deadline_") as temporary:
        directory = Path(temporary)
        (directory / "ssg_deadline_implementation.inc").write_text("".join(pieces))
        binary = directory / "ssg_deadline"
        subprocess.run([os.environ.get("CXX", "c++"), "-std=c++20", "-Wall", "-Wextra", "-Werror",
                        "-I", str(directory), "-I", str(repo_root / "src/user/include"),
                        "-I", str(repo_root / "src/shared/include"),
                        str(repo_root / "tests/ssg_deadline_host_test.cpp"), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
