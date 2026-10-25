// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <sys/times.h>

extern "C" clock_t _times(struct tms*);

// newlib's clock() reaches the platform through _times_r() -> times(), but the
// SDK archive ships no public times() wrapper. XOS has no CPU-time accounting,
// so _times() reports ENOSYS and time.process_time() fails at runtime instead
// of returning invented values.
extern "C" clock_t times(struct tms* buffer) {
    return _times(buffer);
}

// XOS has no blocking sleep service. Spin on the PIT tick counter instead: the
// delay is real, but it consumes CPU. No signal can interrupt it. CPython's
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
