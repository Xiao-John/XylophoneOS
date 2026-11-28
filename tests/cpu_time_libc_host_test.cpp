// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/thread_core.hpp>
#include <pthread.h>
#include <sys/times.h>
#include <time.h>
#include <errno.h>
#include <cstdio>
#include <climits>

namespace {
xos::process_cpu_time reading{};
xos::i64 query_result;
int test_errno;
int skew_case, sample_index, join_index;
xos::u64 join_deadlines[4];
}
extern "C" int* __errno() { return &test_errno; }
namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    if (skew_case && (number == sys_clock_monotonic || number == sys_clock_realtime)) {
        if (skew_case == 1) {
            bool first_sample = sample_index++ == 0;
            return number == sys_clock_monotonic ? (first_sample ? 100000000000L : 102000000000L)
                                                : (first_sample ? 10000000000L : 12000000000L);
        }
        int pair = sample_index++ / 2;
        if (!pair) { return number == sys_clock_monotonic ? 100000000000L : 10400000000L; }
        return number == sys_clock_monotonic ? (skew_case == 2 ? 100600000000L : 101000000000L)
                                            : (skew_case == 2 ? 10600000000L : 11000000000L);
    }
    if (skew_case && number == sys_thread_join) {
        auto& options = *reinterpret_cast<thread_join_options*>(third);
        if (first != 7 || options.header.version != 1 || options.header.size != 32 ||
            options.header.reserved || options.mode != thread_join_mode::deadline || join_index >= 4) { __builtin_trap(); }
        join_deadlines[join_index++] = options.deadline_ns;
        if (skew_case == 2 && join_index == 2) { *reinterpret_cast<u64*>(second) = 0x125; return 0; }
        return skew_case == 4 ? process_error_invalid : thread_error_timeout;
    }
    if (number == sys_thread_info && second == thread_info_cpu_time && third == 0) {
        auto& value = *reinterpret_cast<thread_cpu_time*>(first);
        if (value.header.version != 1 || value.header.size != sizeof(value) || value.tid != 7) { __builtin_trap(); }
        if (query_result == 0) { value.user_ns = 4000000; value.system_ns = 1000000; value.resolution_ns = 2; }
        return query_result;
    }
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
#define pthread_join tested_join
#define pthread_tryjoin_np tested_tryjoin
#define pthread_timedjoin_np tested_timedjoin
#include "join_pthread.inc"
#undef pthread_join
#undef pthread_tryjoin_np
#undef pthread_timedjoin_np

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
    static_assert(sizeof(clockid_t) == sizeof(unsigned long));
    const clockid_t target_clock = static_cast<clockid_t>(-8);
    if (tested_gettime(target_clock, &value) || value.tv_sec || value.tv_nsec != 5000000) { return 10; }
    if (tested_getres(target_clock, &value) || value.tv_sec || value.tv_nsec != 2) { return 11; }
    query_result = thread_error_not_found;
    if (tested_gettime(target_clock, &value) != -1 || errno != ESRCH || value.tv_nsec != 2) { return 12; }
    query_result = xos::process_cpu_time_unavailable;
    if (tested_clock() != static_cast<clock_t>(-1) || errno != ENOTSUP) { return 3; }
    if (tested_times(nullptr) != static_cast<clock_t>(-1) || errno != EFAULT) { return 4; }
    if (tested_gettime(CLOCK_THREAD_CPUTIME_ID, &value) != -1 || errno != ENOTSUP) { return 8; }
    query_result = xos::process_error_resources;
    if (tested_times(&result) != static_cast<clock_t>(-1) || errno != ENOMEM) { return 9; }
    timespec limit{11, 0};
    void* returned = reinterpret_cast<void*>(0x888);
    skew_case = 1; sample_index = join_index = 0;
    if (tested_timedjoin(7, &returned, &limit) != ETIMEDOUT || join_index != 1 ||
        join_deadlines[0] != 0 || returned != reinterpret_cast<void*>(0x888)) { return 13; }
    skew_case = 2; sample_index = join_index = 0;
    if (tested_timedjoin(7, &returned, &limit) != 0 || join_index != 2 ||
        join_deadlines[0] != 100600000000UL || join_deadlines[1] != 101000000000UL ||
        returned != reinterpret_cast<void*>(0x125)) { return 14; }
    skew_case = 3; sample_index = join_index = 0; returned = reinterpret_cast<void*>(0x888);
    if (tested_timedjoin(7, &returned, &limit) != ETIMEDOUT || join_index != 2 ||
        join_deadlines[0] != 100600000000UL || join_deadlines[1] != 0 ||
        returned != reinterpret_cast<void*>(0x888)) { return 15; }
    skew_case = 4; sample_index = join_index = 0;
    if (tested_timedjoin(7, &returned, &limit) != EINVAL || join_index != 1 ||
        returned != reinterpret_cast<void*>(0x888)) { return 16; }
    std::puts("PASS real newlib times/clock and pthread CPU clocks, process-only clock, sleep exclusion and unavailable error");
    std::puts("PASS real legacy timedjoin: preemption skew, early timeout retry, expired atomic check and old-kernel rejection");
}
