/* SPDX-License-Identifier: Apache-2.0 */
/* POSIX clock functions: clock_gettime / clock_getres / clock_settime /
   clock_nanosleep / nanosleep.  Mapped onto the kernel monotonic and wall
   clocks; no new syscalls required. */
#include <errno.h>
#include <stdint.h>
#include <time.h>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>
#include <xos/process_abi.hpp>

// The x86_64-elf newlib feature header does not set _POSIX_MONOTONIC_CLOCK
// (it is gated behind __rtems__/__CYGWIN__), so CLOCK_MONOTONIC is absent
// unless a consumer defines it.  Match the values from <time.h>.
#ifndef CLOCK_REALTIME
#define CLOCK_REALTIME 1
#endif
#ifndef CLOCK_MONOTONIC
#define CLOCK_MONOTONIC 4
#endif
#ifndef CLOCK_MONOTONIC_RAW
#define CLOCK_MONOTONIC_RAW 5
#endif
#ifndef CLOCK_REALTIME_COARSE
#define CLOCK_REALTIME_COARSE 0
#endif
#ifndef CLOCK_MONOTONIC_COARSE
#define CLOCK_MONOTONIC_COARSE 6
#endif
#ifndef TIMER_ABSTIME
#define TIMER_ABSTIME 4
#endif

namespace {
constexpr xos::u64 nanoseconds_per_second = 1'000'000'000ull;

xos::i64 clock_ns(int clock_id) {
    switch (clock_id) {
    case CLOCK_REALTIME:
    case CLOCK_REALTIME_COARSE:
        return xos::sdk::syscall(xos::sys_clock_realtime, 0);
    case CLOCK_MONOTONIC:
    case CLOCK_MONOTONIC_RAW:
    case CLOCK_MONOTONIC_COARSE:
        return xos::sdk::syscall(xos::sys_clock_monotonic, 0);
    default:
        return -1;
    }
}

void ns_to_timespec(xos::u64 ns, struct timespec* ts) {
    ts->tv_sec = static_cast<time_t>(ns / nanoseconds_per_second);
    ts->tv_nsec = static_cast<long>(ns % nanoseconds_per_second);
}

bool timespec_to_ns(const struct timespec* ts, xos::u64& ns) {
    // The caller has validated nonnegative seconds and normalized nanoseconds.
    const xos::u64 seconds = static_cast<xos::u64>(ts->tv_sec);
    const xos::u64 nanoseconds = static_cast<xos::u64>(ts->tv_nsec);
    if (seconds > (static_cast<xos::u64>(INT64_MAX) - nanoseconds) /
                      nanoseconds_per_second) {
        return false;
    }
    ns = seconds * nanoseconds_per_second + nanoseconds;
    return true;
}
}  // namespace

extern "C" int clock_gettime(clockid_t clock_id, struct timespec* tp) {
    if (tp == nullptr) { errno = EFAULT; return -1; }
    const xos::i64 now = clock_ns(clock_id);
    if (now < 0) { errno = EINVAL; return -1; }
    ns_to_timespec(static_cast<xos::u64>(now), tp);
    return 0;
}

extern "C" int clock_getres(clockid_t clock_id, struct timespec* res) {
    switch (clock_id) {
    case CLOCK_REALTIME:
    case CLOCK_REALTIME_COARSE:
        // Wall clock has nanosecond resolution (syscall returns ns).
        if (res != nullptr) { res->tv_sec = 0; res->tv_nsec = 1; }
        return 0;
    case CLOCK_MONOTONIC:
    case CLOCK_MONOTONIC_RAW:
    case CLOCK_MONOTONIC_COARSE:
        // Monotonic clock is driven by the scheduler tick (10 ms).
        if (res != nullptr) { res->tv_sec = 0; res->tv_nsec = 10'000'000; }
        return 0;
    default:
        errno = EINVAL;
        return -1;
    }
}

extern "C" int clock_settime(clockid_t, const struct timespec*) {
    // The kernel provides no wall-clock setter; POSIX allows EPERM.
    errno = EPERM;
    return -1;
}

extern "C" int clock_nanosleep(clockid_t clock_id, int flags,
                                const struct timespec* req, struct timespec* rem) {
    if (req == nullptr) { return EFAULT; }
    if (req->tv_nsec < 0 || req->tv_nsec >= static_cast<long>(nanoseconds_per_second) ||
        req->tv_sec < 0) {
        return EINVAL;
    }
    if (flags != 0 && flags != TIMER_ABSTIME) { return EINVAL; }

    // Validate clock_id before entering either branch.
    const bool is_monotonic = clock_id == CLOCK_MONOTONIC ||
                              clock_id == CLOCK_MONOTONIC_RAW ||
                              clock_id == CLOCK_MONOTONIC_COARSE;
    const bool is_realtime = clock_id == CLOCK_REALTIME ||
                             clock_id == CLOCK_REALTIME_COARSE;
    if (!is_monotonic && !is_realtime) { return EINVAL; }

    xos::u64 request_ns;
    if (!timespec_to_ns(req, request_ns)) { return EINVAL; }

    if (flags == TIMER_ABSTIME) {
        if (is_monotonic) {
            // Monotonic absolute: use the request deadline directly.
            const xos::u64 deadline = request_ns;
            const xos::i64 now = xos::sdk::syscall(xos::sys_clock_monotonic, 0);
            if (now < 0) { return EIO; }
            if (static_cast<xos::u64>(now) >= deadline) { return 0; }
            const xos::i64 result = xos::sdk::syscall(xos::sys_sleep_until, deadline);
            return result < 0 ? EIO : 0;
        }
        // Realtime absolute: convert through the current wall-to-monotonic
        // offset, then re-check after waking to correct for preempt delay.
        for (;;) {
            const xos::i64 monotonic_now = xos::sdk::syscall(xos::sys_clock_monotonic, 0);
            const xos::i64 wall_now = xos::sdk::syscall(xos::sys_clock_realtime, 0);
            if (monotonic_now < 0 || wall_now < 0) { return EIO; }
            const xos::u64 wall_deadline = request_ns;
            const xos::i64 wall_delta = static_cast<xos::i64>(wall_deadline)
                                      - static_cast<xos::i64>(wall_now);
            if (wall_delta <= 0) { return 0; }
            const xos::u64 monotonic_deadline =
                static_cast<xos::u64>(monotonic_now) + static_cast<xos::u64>(wall_delta);
            const xos::i64 result = xos::sdk::syscall(xos::sys_sleep_until, monotonic_deadline);
            if (result < 0) { return EIO; }
            // Re-check: the conversion used a sample from before the sleep.
        }
    }

    // Relative sleep.
    const xos::i64 monotonic_now = xos::sdk::syscall(xos::sys_clock_monotonic, 0);
    if (monotonic_now < 0) { return EIO; }
    const xos::u64 duration = request_ns;
    const xos::u64 monotonic_deadline = static_cast<xos::u64>(monotonic_now) + duration;
    const xos::i64 result = xos::sdk::syscall(xos::sys_sleep_until, monotonic_deadline);
    if (result < 0) {
        if (rem != nullptr) {
            const xos::i64 after = xos::sdk::syscall(xos::sys_clock_monotonic, 0);
            const xos::u64 remaining = monotonic_deadline > static_cast<xos::u64>(after)
                ? monotonic_deadline - static_cast<xos::u64>(after) : 0;
            ns_to_timespec(remaining, rem);
        }
        return result == xos::process_error_would_block ? EAGAIN : EIO;
    }
    return 0;
}

extern "C" int nanosleep(const struct timespec* req, struct timespec* rem) {
    const int code = clock_nanosleep(CLOCK_MONOTONIC, 0, req, rem);
    if (code != 0) { errno = code; return -1; }
    return 0;
}
