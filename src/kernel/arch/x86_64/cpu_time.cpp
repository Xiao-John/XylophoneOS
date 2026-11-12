// SPDX-License-Identifier: Apache-2.0
#include "cpu_time.hpp"
#include <xos/clock.hpp>

namespace xos::arch {
namespace {
u64 cycles_per_tick;

bool next_tick(u64 after, u64& tick, u64& counter) {
    // No HLT here: a missing timer must fail calibration, not hang boot.
    for (u32 attempts = 0; attempts < 100000000; ++attempts) {
        __asm__ volatile("sti; pause; cli" ::: "memory");
        tick = clock::ticks();
        if (tick != after) { counter = execution_counter(); return true; }
    }
    return false;
}
}

u64 execution_counter() {
    u32 low, high;
    __asm__ volatile("lfence; rdtsc" : "=a"(low), "=d"(high) :: "memory");
    return (static_cast<u64>(high) << 32) | low;
}

bool execution_clock_init() {
    u32 eax = 1, ebx, ecx = 0, edx;
    __asm__ volatile("cpuid" : "+a"(eax), "=b"(ebx), "+c"(ecx), "=d"(edx));
    if (!(edx & (1u << 4))) { return false; }
    u64 first_tick = 0, first_counter = 0, last_tick = 0, last_counter = 0;
    if (!next_tick(clock::ticks(), first_tick, first_counter)) { return false; }
    last_tick = first_tick;
    while (last_tick - first_tick < 4) {
        if (!next_tick(last_tick, last_tick, last_counter)) { return false; }
    }
    if (last_counter <= first_counter) { return false; }
    const u64 measured = (last_counter - first_counter) / (last_tick - first_tick);
    // This bound also keeps remainder * resolution_ns within u64 below.
    if (measured < 1000 || measured > 1000000000000ull) { return false; }
    cycles_per_tick = measured;
    return true;
}

u64 execution_time_ns(u64 cycles) {
    const u64 whole = cycles / cycles_per_tick;
    const u64 fraction = (cycles % cycles_per_tick) * clock::resolution_ns / cycles_per_tick;
    if (whole > (~u64{0} - fraction) / clock::resolution_ns) { return ~u64{0}; }
    return whole * clock::resolution_ns + fraction;
}

u64 execution_resolution_ns() {
    return (clock::resolution_ns + cycles_per_tick - 1) / cycles_per_tick;
}
}
