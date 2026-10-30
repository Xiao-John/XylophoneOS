// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/terminal_control.hpp>
#include <xos/thread_abi.hpp>
#include "shell_terminal.hpp"

namespace xos::user::shell_terminal {
namespace {
enum class mode : u32 { legacy, active, unavailable };
mode current_mode;
terminal::control session;
}

i64 start(const char* path) {
    if (current_mode != mode::legacy) return process_error_state;
    // Once handoff is attempted, its failure cannot prove that the original
    // console still owns COM1. Do not silently fall back to the old console.
    current_mode = mode::unavailable;
    const i64 result = terminal::start(session, path);
    if (result > 0) current_mode = mode::active;
    return result;
}

extern "C" i64 xos_console_read_hook(u32 handle, void* data, u64 length) {
    if (current_mode == mode::legacy)
        return sdk::syscall(sys_handle_read, handle, reinterpret_cast<u64>(data), length);
    if (current_mode != mode::active) return process_error_state;
    const i64 now = sdk::syscall(sys_clock_monotonic);
    if (now < 0) return now;
    const u64 time = static_cast<u64>(now);
    const u64 deadline = time >= thread_deadline_infinite - thread_tick_ns
        ? thread_deadline_infinite - 1 : time + thread_tick_ns;
    const u32 amount = length > terminal::data_bytes ? terminal::data_bytes : static_cast<u32>(length);
    const i64 result = terminal::read_until(session, data, amount, deadline);
    // Existing Xsh treats a zero read as an idle poll, not as EOF.
    return result == thread_error_timeout ? 0 : result;
}

extern "C" i64 xos_console_write_hook(u32 handle, const void* data, u64 length) {
    if (current_mode == mode::legacy)
        return sdk::syscall(sys_handle_write, handle, reinterpret_cast<u64>(data), length);
    if (current_mode != mode::active) return process_error_state;
    const u32 amount = length > terminal::data_bytes ? terminal::data_bytes : static_cast<u32>(length);
    return terminal::write_until(session, data, amount, thread_deadline_infinite);
}
}
