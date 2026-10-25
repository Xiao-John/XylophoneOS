// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/thread_abi.hpp>

namespace xos {
enum class thread_state : u32 { free, reserved, fresh, ready, running, blocked, dead };
enum class thread_wait_kind : u32 { none, process, join, word, sleep, exit_barrier, pipe_read, pipe_write };

// No ISA state or kernel pointers in the shared lifecycle contract.
struct thread_lifetime {
    u64 tid;
    thread_state state;
    thread_wait_kind wait_kind;
    bool detached;
    bool leaving;
    bool reaped;
    bool main;
    u64 joiner;
    u64 result;
    u64 wait_target;
    u64 wait_buffer;
    u64 deadline_ns;
    u64 wait_order;
    u64 stack_bottom;
    u64 stack_top;
    u64 tls_begin;
    u64 tls_end;
};
inline bool thread_has_user_work(const thread_lifetime& thread) {
    return thread.state != thread_state::free && thread.state != thread_state::reserved &&
           thread.state != thread_state::dead && !thread.leaving;
}
inline bool thread_deadline_reached(u64 now, u64 deadline) {
    return deadline != thread_deadline_infinite && now >= deadline;
}
}
