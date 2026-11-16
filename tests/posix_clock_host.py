# SPDX-License-Identifier: Apache-2.0
"""Exercise the real clock sleep implementation with deterministic syscall stubs."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="xos_clock_host_") as folder:
        folder = Path(folder)
        include = folder / "xos"
        include.mkdir()
        (include / "sdk.hpp").write_text('''#pragma once
#include <stdint.h>
namespace xos {
using u64 = uint64_t;
using i64 = int64_t;
constexpr int sys_clock_monotonic = 1, sys_clock_realtime = 2, sys_sleep_until = 3;
constexpr i64 process_error_would_block = -2;
namespace sdk { i64 syscall(int, u64); }
}
''')
        for header in ("thread_abi.hpp", "process_abi.hpp"):
            (include / header).write_text("#pragma once\n")
        # Avoid host libc attributes/exception specifications on XOS definitions.
        (folder / "time.h").write_text('''#pragma once
using time_t = long;
using clockid_t = int;
struct timespec { time_t tv_sec; long tv_nsec; };
#define CLOCK_REALTIME 1
#define CLOCK_MONOTONIC 4
#define CLOCK_MONOTONIC_RAW 5
#define CLOCK_REALTIME_COARSE 0
#define CLOCK_MONOTONIC_COARSE 6
#define TIMER_ABSTIME 4
extern "C" int clock_nanosleep(clockid_t, int, const timespec*, timespec*);
extern "C" int nanosleep(const timespec*, timespec*);
''')
        source = folder / "probe.cpp"
        source.write_text('''#include <cassert>
#include <stdint.h>
#include <time.h>
#include <xos/sdk.hpp>
static xos::i64 now;
static xos::u64 slept_until;
static int calls, sleeps;
xos::i64 xos::sdk::syscall(int id, xos::u64 value) {
    ++calls;
    if (id == xos::sys_sleep_until) {
        ++sleeps;
        slept_until = value;
        now = static_cast<xos::i64>(value);
        return 0;
    }
    return now;
}
int main() {
    const int clocks[] = {CLOCK_MONOTONIC, CLOCK_MONOTONIC_RAW,
                          CLOCK_MONOTONIC_COARSE, CLOCK_REALTIME,
                          CLOCK_REALTIME_COARSE};
    const timespec invalid[] = {
        {9223372036LL, 854775808}, // INT64_MAX + 1 ns
        {9223372037LL, 0},
        {18446744074LL, 0}, // would wrap uint64_t
        {INT64_MAX, 999999999},
        {-1, 0}, {0, -1}, {0, 1000000000}
    };
    for (int clock : clocks) {
        for (int flags : {0, TIMER_ABSTIME}) {
            for (const auto& req : invalid) {
                calls = 0;
                timespec rem = {7, 8};
                errno = 123;
                assert(clock_nanosleep(clock, flags, &req, &rem) == EINVAL);
                assert(calls == 0 && rem.tv_sec == 7 && rem.tv_nsec == 8);
                assert(errno == 123);
            }
            for (xos::i64 ns : {0LL, 1LL, 999999999LL, 1000000000LL,
                               INT64_MAX - 1LL, static_cast<long long>(INT64_MAX)}) {
                timespec req = {ns / 1000000000, ns % 1000000000};
                now = 0;
                sleeps = 0;
                assert(clock_nanosleep(clock, flags, &req, nullptr) == 0);
                if (flags == 0 || ns > 0) {
                    assert(sleeps == 1 && slept_until == static_cast<xos::u64>(ns));
                } else {
                    assert(sleeps == 0);
                }
            }
        }
    }
    calls = 0;
    errno = 0;
    assert(nanosleep(&invalid[0], nullptr) == -1 && errno == EINVAL);
    assert(calls == 0);
    timespec past = {0, 1};
    now = 2;
    sleeps = 0;
    assert(clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &past, nullptr) == 0);
    assert(clock_nanosleep(CLOCK_REALTIME, TIMER_ABSTIME, &past, nullptr) == 0);
    assert(sleeps == 0);
}
'''.replace('#include <cassert>', '#include <cassert>\n#include <cerrno>\n#include <initializer_list>'))
        # Rename exported libc symbols to avoid interposing on the host runtime.
        renames = [f"-D{name}=xos_test_{name}" for name in
                   ("clock_gettime", "clock_getres", "clock_settime",
                    "clock_nanosleep", "nanosleep")]
        executable = folder / "probe"
        subprocess.run([os.environ.get("CXX", "g++"), "-std=c++20", "-Wall",
                        "-Wextra", "-Werror", "-fsanitize=undefined",
                        "-fno-sanitize-recover=all", *renames, "-I", str(folder),
                        str(ROOT / "src/user/libc/posix_clock.cpp"), str(source),
                        "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
    print("posix_clock_host: passed")


if __name__ == "__main__":
    main()
