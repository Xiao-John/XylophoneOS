// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <sys/times.h>

extern "C" clock_t _times(struct tms*);

// Older SDKs have no public times() wrapper. Keep a weak fallback so SDKs
// that supply the wrapper can provide their own definition.
extern "C" __attribute__((weak)) clock_t times(struct tms* buffer) {
    return _times(buffer);
}

// This compatibility bridge still spins instead of using the threading
// profile's blocking sleep service. No signal can interrupt it. CPython's
// time.sleep() calls this directly because newlib hides nanosleep() behind an
// unset _POSIX_TIMERS visibility level.
extern "C" void xos_cpython_sleep_ns(long long nanoseconds) {
    constexpr xos::u64 ns_per_tick = 10000000;
    if (nanoseconds <= 0) {
        return;
    }
    const xos::u64 ticks =
        (static_cast<xos::u64>(nanoseconds) + ns_per_tick - 1) / ns_per_tick;
    const xos::u64 deadline = xos::sdk::ticks() + ticks;
    while (xos::sdk::ticks() < deadline) {
    }
}

extern "C" long long xos_cpython_monotonic_ns() {
    constexpr xos::u64 ns_per_tick = 10000000;
    constexpr xos::u64 max_signed = 0x7fffffffffffffffULL;
    const xos::u64 ticks = xos::sdk::ticks();
    if (ticks > max_signed / ns_per_tick) {
        return static_cast<long long>(max_signed);
    }
    return static_cast<long long>(ticks * ns_per_tick);
}
