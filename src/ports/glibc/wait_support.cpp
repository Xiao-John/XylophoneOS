// SPDX-License-Identifier: Apache-2.0
#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <sys/wait.h>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

extern "C" long __xos_wait_child(pid_t pid, int* status, int options) {
    using namespace xos;
    if ((pid <= 0 && pid != -1) || (options & ~WNOHANG) != 0) { return -ENOTSUP; }
    const bool nonblocking = (options & WNOHANG) != 0;
    const bool any = pid == -1;
    process_status waited{};
    const i64 result = sdk::syscall(sys_process_wait, any ? 0 : static_cast<u64>(pid),
        reinterpret_cast<u64>(&waited),
        (nonblocking ? process_wait_nonblocking : 0) | (any ? process_wait_any : 0));
    if (result == process_error_denied) { return -ECHILD; }
    if (result == process_error_would_block && nonblocking) { return 0; }
    if (result == thread_error_busy || result == process_error_state) { return -EBUSY; }
    if (result == thread_error_address) { return -EFAULT; }
    if (result != 0 || waited.version != 1 || waited.pid == 0 || waited.pid > INT_MAX ||
        (!any && waited.pid != static_cast<u64>(pid))) { return -EIO; }

    int encoded;
    switch (waited.outcome) {
    case process_outcome::exited:
        encoded = static_cast<int>((static_cast<u64>(waited.code) & 0xffu) << 8);
        break;
    case process_outcome::faulted:
    case process_outcome::killed:
        // Match the native newlib projection for XOS abnormal termination.
        encoded = SIGKILL;
        break;
    default: return -EIO;
    }
    if (status != nullptr) { *status = encoded; }
    return static_cast<long>(waited.pid);
}
