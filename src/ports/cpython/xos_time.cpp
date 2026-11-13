// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>
#include <errno.h>
#include <sys/times.h>

extern "C" clock_t _times(struct tms*);

// Older SDKs have no public times() wrapper. Keep a weak fallback so SDKs
// that supply the wrapper can provide their own definition.
extern "C" __attribute__((weak)) clock_t times(struct tms* buffer) {
    return _times(buffer);
}

extern "C" int xos_cpython_sleep_ns(long long nanoseconds) {
    if (nanoseconds < 0) { errno = EINVAL; return -1; }
    const xos::i64 now = xos::sdk::syscall(xos::sys_clock_monotonic);
    if (now < 0) { errno = EIO; return -1; }
    const xos::u64 duration = static_cast<xos::u64>(nanoseconds);
    if (duration > xos::thread_deadline_infinite - 1 - static_cast<xos::u64>(now)) {
        errno = EOVERFLOW; return -1;
    }
    const xos::i64 result = xos::sdk::syscall(xos::sys_sleep_until,
        static_cast<xos::u64>(now) + duration);
    if (result < 0) { errno = result == xos::thread_error_unsupported ? ENOSYS : EIO; return -1; }
    return 0;
}

extern "C" long long xos_cpython_monotonic_ns() {
    const xos::i64 result = xos::sdk::syscall(xos::sys_clock_monotonic);
    if (result < 0) { errno = EIO; return -1; }
    return result;
}

extern "C" long long xos_cpython_clock_resolution_ns() {
    const xos::i64 result = xos::sdk::syscall(xos::sys_clock_monotonic, 1);
    if (result <= 0) { errno = EIO; return -1; }
    return result;
}
