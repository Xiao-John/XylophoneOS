// SPDX-License-Identifier: Apache-2.0
#define _POSIX_C_SOURCE 200809L
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>
#include <sys/times.h>
#include <time.h>
#include <stdio.h>
#include <unistd.h>

int main() {
    xos::process_cpu_time before{}, busy{}, slept{};
    if (xos::sdk::cpu_time(before) != 0) { puts("[cpu-time] unavailable"); return 1; }
    xos::u64 value = 1;
    for (xos::u64 i = 0; i < 20000000; ++i) {
        value = value * 6364136223846793005ull + 1;
        __asm__ volatile("" : "+r"(value));
    }
    if (xos::sdk::cpu_time(busy) != 0 || busy.user_ns <= before.user_ns || busy.system_ns == 0) return 2;
    if (xos::sdk::syscall(xos::sys_sleep_until, busy.elapsed_ns + 100000000) != 0 ||
        xos::sdk::cpu_time(slept) != 0) return 3;
    const auto elapsed = slept.elapsed_ns - busy.elapsed_ns;
    const auto cpu = slept.user_ns - busy.user_ns + slept.system_ns - busy.system_ns;
    if (elapsed < 100000000 || cpu >= elapsed / 2) return 4;
    tms totals{};
    if (times(&totals) == static_cast<clock_t>(-1) || clock() == static_cast<clock_t>(-1) ||
        sysconf(_SC_CLK_TCK) != CLOCKS_PER_SEC) return 5;
    puts("[cpu-time] user_system_sleep_times=PASS");
    return 0;
}
