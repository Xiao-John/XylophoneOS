// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/thread_abi.hpp>
#include <xos/sdk.hpp>

// Mechanism-only API for T0/T1 probes. It does not make the single-thread libc
// archive safe. General applications must use the separately validated profile.
namespace xos::thread {
inline i64 info(thread_info& value) { return sdk::syscall(sys_thread_info, reinterpret_cast<u64>(&value)); }
inline u64 self() { thread_info value{}; return info(value) == 0 ? value.tid : 0; }
inline u64 clock() { return static_cast<u64>(sdk::syscall(sys_clock_monotonic)); }
inline i64 sleep_until(u64 deadline) { return sdk::syscall(sys_sleep_until, deadline); }
inline i64 wait(u32* address, u32 expected, u64 deadline = thread_deadline_infinite) {
    thread_wait_request request{{thread_abi_version, sizeof(thread_wait_request), 0},
        reinterpret_cast<u64>(address), deadline, expected, 0};
    return sdk::syscall(sys_wait_word, reinterpret_cast<u64>(&request));
}
inline i64 wake(u32* address, u32 count = 1) {
    return sdk::syscall(sys_wake_word, reinterpret_cast<u64>(address), count);
}
inline i64 enable() {
    thread_header header{thread_abi_version, sizeof(thread_header), 0};
    return sdk::syscall(sys_thread_profile, reinterpret_cast<u64>(&header));
}
inline i64 join(u64 tid, u64& value) { return sdk::syscall(sys_thread_join, tid, reinterpret_cast<u64>(&value)); }
inline i64 detach(u64 tid) { return sdk::syscall(sys_thread_detach, tid); }
// Initializes only static TLS and a tiny entry record. No malloc, global
// constructors, newlib reent, pthread TSS or C++ destructor registration here.
using entry_function = u64 (*)(void*);
i64 create(u64& tid, entry_function entry, void* argument, u64 stack_bytes = thread_stack_default,
           bool detached = false);
[[noreturn]] void exit(u64 value);
}
