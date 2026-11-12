# SPDX-License-Identifier: Apache-2.0
"""Run the real Adventure readline shim against host pipes, including EOF."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

repo_root = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=repo_root / "src/ports/adventure/xos_readline.cpp")
    args = parser.parse_args()
    program = r'''
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <unistd.h>
#include <xos/sdk.hpp>
extern "C" char* readline(const char*);
namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    if (number == sys_handle_read) {
        return ::read(static_cast<int>(first), reinterpret_cast<void*>(second), third);
    }
    if (number == sys_handle_write) { return static_cast<i64>(third); }
    // None of the prepared pipes has a live writer, so EOF cannot need a yield.
    assert(false && "readline spun after pipe EOF");
    return -1;
}
}
static void input(const char* value) {
    int descriptors[2];
    assert(pipe(descriptors) == 0);
    const auto length = std::strlen(value);
    assert(write(descriptors[1], value, length) == static_cast<ssize_t>(length));
    assert(close(descriptors[1]) == 0);
    assert(dup2(descriptors[0], 0) == 0);
    assert(close(descriptors[0]) == 0);
}
int main() {
    input("");
    assert(readline("prompt> ") == nullptr);
    input("look");
    char* line = readline(nullptr);
    assert(line != nullptr && std::strcmp(line, "look") == 0);
    std::free(line);
    assert(readline(nullptr) == nullptr);
    input("north\n");
    line = readline(nullptr);
    assert(line != nullptr && std::strcmp(line, "north") == 0);
    std::free(line);
    assert(readline(nullptr) == nullptr);
}
'''
    with tempfile.TemporaryDirectory(prefix="xos_adventure_readline_") as temporary:
        directory = Path(temporary)
        source = directory / "test.cpp"
        source.write_text(program)
        binary = directory / "readline_test"
        subprocess.run([
            os.environ.get("CXX", "c++"), "-std=c++20", "-Wall", "-Wextra", "-Werror",
            "-I", str(repo_root / "src/user/include"), "-I", str(repo_root / "src/shared/include"),
            str(source), str(args.source.resolve()),
            "-o", str(binary),
        ], check=True)
        subprocess.run([str(binary)], check=True)
    print("PASS Adventure readline: empty EOF, partial line EOF, newline and subsequent EOF")


if __name__ == "__main__":
    main()
