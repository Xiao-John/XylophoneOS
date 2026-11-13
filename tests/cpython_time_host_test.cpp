// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>
#include <cassert>
#include <cerrno>
#include <sys/times.h>

extern "C" int xos_cpython_sleep_ns(long long);
extern "C" long long xos_cpython_monotonic_ns();
extern "C" long long xos_cpython_clock_resolution_ns();
extern "C" clock_t _times(tms*) { return 0; }

namespace {
xos::i64 now = 30000000, resolution = 10000000, sleep_result;
xos::u64 observed_deadline;
unsigned sleeps;
}

namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64, u64) {
    if (number == sys_clock_monotonic) return first == 0 ? now : resolution;
    assert(number == sys_sleep_until);
    observed_deadline = first;
    ++sleeps;
    return sleep_result;
}
}

int main() {
    assert(xos_cpython_monotonic_ns() == now);
    assert(xos_cpython_clock_resolution_ns() == resolution);
    assert(xos_cpython_sleep_ns(15000001) == 0);
    assert(sleeps == 1 && observed_deadline == 45000001);
    assert(xos_cpython_sleep_ns(0) == 0 && sleeps == 2);
    assert(xos_cpython_sleep_ns(-1) == -1 && errno == EINVAL && sleeps == 2);
    now = -1;
    assert(xos_cpython_monotonic_ns() == -1 && errno == EIO);
    assert(xos_cpython_sleep_ns(1) == -1 && sleeps == 2);
    now = 30000000;
    sleep_result = xos::thread_error_unsupported;
    assert(xos_cpython_sleep_ns(1) == -1 && errno == ENOSYS);
    sleep_result = xos::process_error_state;
    assert(xos_cpython_sleep_ns(1) == -1 && errno == EIO);
    resolution = 0;
    assert(xos_cpython_clock_resolution_ns() == -1 && errno == EIO);
}
