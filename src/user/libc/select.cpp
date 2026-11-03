// SPDX-License-Identifier: Apache-2.0
#define _POSIX_C_SOURCE 200809L
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>
#include <xos/terminal_abi.hpp>
#include <errno.h>
#include <sys/select.h>
using xos::u64;
extern "C" xos::i64 xos_libc_terminal_wait_readable(int, u64);
static int wait_error(xos::i64 result) {
    return result == xos::terminal::interrupted ? EINTR :
        result == xos::process_error_invalid ? EBADF :
        result == xos::thread_error_unsupported ? ENOTSUP : EIO;
}

// Initial single-terminal read subset. Unsupported descriptor combinations
// fail explicitly; they are not reported as timed out or ready.
extern "C" int select(int nfds, fd_set* readfds, fd_set* writefds, fd_set* exceptfds,
                      struct timeval* timeout) {
    if (nfds < 0 || nfds > FD_SETSIZE ||
        (timeout && (timeout->tv_sec < 0 || timeout->tv_usec < 0 || timeout->tv_usec >= 1000000))) {
        errno = EINVAL; return -1;
    }
    int selected = -1;
    for (int fd = 0; fd < nfds; ++fd) {
        if ((writefds && FD_ISSET(fd, writefds)) || (exceptfds && FD_ISSET(fd, exceptfds))) {
            errno = ENOTSUP; return -1;
        }
        if (readfds && FD_ISSET(fd, readfds)) {
            if (selected >= 0) { errno = ENOTSUP; return -1; }
            selected = fd;
        }
    }
    if (selected < 0) { errno = ENOTSUP; return -1; }
    u64 deadline = xos::thread_deadline_infinite;
    if (timeout) {
        const xos::i64 now = xos::sdk::syscall(xos::sys_clock_monotonic);
        if (now < 0) { errno = EIO; return -1; }
        const u64 max = xos::thread_deadline_infinite - 1;
        const u64 seconds = static_cast<u64>(timeout->tv_sec);
        const u64 micros = static_cast<u64>(timeout->tv_usec);
        const u64 room = max - static_cast<u64>(now);
        const u64 fraction = micros * 1000;
        deadline = fraction > room || seconds > (room - fraction) / 1000000000ull
            ? max : static_cast<u64>(now) + seconds * 1000000000ull + fraction;
    }
    const xos::i64 result = xos_libc_terminal_wait_readable(selected, deadline);
    if (result < 0 && result != xos::thread_error_timeout) {
        errno = wait_error(result); return -1;
    }
    FD_ZERO(readfds);
    if (writefds) FD_ZERO(writefds);
    if (exceptfds) FD_ZERO(exceptfds);
    if (result == 1) { FD_SET(selected, readfds); return 1; }
    return 0;
}
