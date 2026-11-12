// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/thread_core.hpp>
#include <pthread.h>
#include <sys/times.h>
#include <time.h>
#include <errno.h>
#include <cstdio>

namespace {
xos::process_cpu_time reading{};
xos::i64 query_result;
int test_errno;
}
extern "C" int* __errno() { return &test_errno; }
namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    if (number != sys_process_cpu_time || second || third) { __builtin_trap(); }
    auto& value = *reinterpret_cast<process_cpu_time*>(first);
    if (value.version != 1 || value.size != sizeof(value)) { __builtin_trap(); }
    if (query_result == 0) { value = reading; }
    return query_result;
}
}
using xos::u64;
#define _times tested_times
#define times tested_public_times
#define clock tested_clock
#include "cpu_libc.inc"
#undef _times
#undef times
#undef clock
using namespace xos;
#define clock_gettime tested_gettime
#define clock_getres tested_getres
#include "cpu_pthread.inc"
#undef clock_gettime
#undef clock_getres

int main() {
    static_assert(CLOCKS_PER_SEC == 1000);
    reading.user_ns = 120000000;
    reading.system_ns = 30000000;
    reading.child_user_ns = 70000000;
    reading.child_system_ns = 9000000;
    reading.elapsed_ns = 10000000000;
    reading.thread_user_ns = 7000000;
    reading.thread_system_ns = 3000000;
    reading.resolution_ns = 1;
    struct tms result{};
    if (tested_public_times(&result) != 10000 || result.tms_utime != 120 ||
        result.tms_stime != 30 || result.tms_cutime != 70 || result.tms_cstime != 9 ||
        tested_clock() != 150) { return 1; }
    reading.elapsed_ns += 5000000000;
    if (tested_clock() != 150) { return 2; }
    timespec value{};
    if (tested_gettime(CLOCK_PROCESS_CPUTIME_ID, &value) || value.tv_sec || value.tv_nsec != 150000000) { return 5; }
    if (tested_gettime(CLOCK_THREAD_CPUTIME_ID, &value) || value.tv_sec || value.tv_nsec != 10000000) { return 6; }
    if (tested_getres(CLOCK_PROCESS_CPUTIME_ID, &value) || value.tv_sec || value.tv_nsec != 1) { return 7; }
    query_result = xos::process_cpu_time_unavailable;
    if (tested_clock() != static_cast<clock_t>(-1) || errno != ENOTSUP) { return 3; }
    if (tested_times(nullptr) != static_cast<clock_t>(-1) || errno != EFAULT) { return 4; }
    if (tested_gettime(CLOCK_THREAD_CPUTIME_ID, &value) != -1 || errno != ENOTSUP) { return 8; }
    query_result = xos::process_error_resources;
    if (tested_times(&result) != static_cast<clock_t>(-1) || errno != ENOMEM) { return 9; }
    std::puts("PASS real newlib times/clock and pthread CPU clocks, process-only clock, sleep exclusion and unavailable error");
}
