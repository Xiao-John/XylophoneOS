// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/process_abi.hpp>

namespace xos {
// E13-T v1. Numbers 0..37 retain their existing process semantics.
inline constexpr u64 sys_thread_prepare = 38, sys_thread_start = 39, sys_thread_abort = 40;
inline constexpr u64 sys_thread_info = 41, sys_thread_begin_exit = 42, sys_thread_exit = 43;
inline constexpr u64 sys_thread_join = 44, sys_thread_detach = 45, sys_clock_monotonic = 46;
inline constexpr u64 sys_sleep_until = 47, sys_wait_word = 48, sys_wake_word = 49;
inline constexpr u64 sys_thread_stats = 50, sys_process_begin_exit = 51, sys_thread_profile = 52;
inline constexpr u32 thread_abi_version = 1, thread_max_per_process = 4, thread_max_total = 32;
inline constexpr u64 thread_arena_begin = 0x70000000, thread_slot_bytes = 0x400000;
inline constexpr u64 thread_arena_end = thread_arena_begin + thread_max_per_process * thread_slot_bytes;
inline constexpr u64 thread_stack_default = 256 * 1024, thread_stack_min = 64 * 1024;
inline constexpr u64 thread_stack_max = 2 * 1024 * 1024, thread_tls_max = 0x120000;
inline constexpr u64 thread_deadline_infinite = ~u64{0}, thread_tick_ns = 10000000;
inline constexpr i64 thread_error_address = -11, thread_error_busy = -12;
inline constexpr i64 thread_error_timeout = -13, thread_value_changed = -14;
inline constexpr i64 thread_error_not_found = -15, thread_error_deadlock = -16;
inline constexpr i64 thread_error_memory = -17, thread_error_unsupported = -18;

struct thread_header { u32 version; u32 size; u64 reserved; };
struct thread_prepare_request { thread_header header; u64 stack_bytes; u64 tls_bytes; u64 flags; };
struct thread_reservation {
    thread_header header;
    u64 tid, stack_bottom, stack_top, tls_begin, tls_end;
};
struct thread_start_request {
    thread_header header;
    u64 tid, entry, argument, stack, thread_pointer;
};
struct thread_info {
    thread_header header;
    u64 pid, tid, stack_bottom, stack_top, thread_pointer;
};
struct thread_wait_request { thread_header header; u64 address; u64 deadline_ns; u32 expected; u32 reserved; };
struct thread_stats {
    thread_header header;
    u32 processes, threads, reserved, waiting, results, free_pages;
    u32 process_user_pages, process_kernel_stack_pages;
};
inline constexpr u64 thread_flag_detached = 1;
static_assert(sizeof(thread_header) == 16 && sizeof(thread_prepare_request) == 40);
static_assert(sizeof(thread_reservation) == 56 && sizeof(thread_start_request) == 56);
static_assert(sizeof(thread_info) == 56 && sizeof(thread_wait_request) == 40);
static_assert(sizeof(thread_stats) == 48);
}
