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
terminal::application application;
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

bool active() { return current_mode == mode::active; }
bool needs_recovery() { return current_mode == mode::unavailable; }

i64 prepare_application(u64 child, void*) {
    if (current_mode != mode::active || application.peer != 0) return process_error_state;
    const i64 result = terminal::attach(session, application, child);
    // A failed control exchange cannot prove whether the service attached.
    if (result != 0) current_mode = mode::unavailable;
    return result;
}

const u32* application_send_handle() { return &application.incoming; }

i64 finish_application() {
    if (current_mode != mode::active || application.peer == 0) return process_error_state;
    const i64 result = terminal::detach(session, application);
    if (result != 0) current_mode = mode::unavailable;
    return result;
}

i64 stop() {
    if (current_mode != mode::active || application.peer != 0) return process_error_state;
    current_mode = mode::unavailable;
    terminal::request message{}; terminal::response response{};
    message.operation = static_cast<u32>(terminal::operation::stop);
    i64 result = terminal::exchange(session, message, response);
    if (result == 0) result = response.result;
    if (result != 0) return result;
    process_status status{};
    result = sdk::wait(session.child, status);
    if (result != 0) return result;
    terminal::close(session);
    return status.outcome == process_outcome::exited && status.code == 0 ? 0 : process_error_state;
}

i64 recover(const char* path) {
    if (current_mode != mode::unavailable || path == nullptr || application.peer != 0)
        return process_error_state;
    if (session.child != 0) {
        process_status status{};
        const i64 reaped = sdk::syscall(sys_process_wait, session.child, reinterpret_cast<u64>(&status), 1);
        if (reaped != 0) return reaped;
        terminal::close(session);
    }
    const i64 state = sdk::pio_grant(pio_grant_action::query, 0, pio_resource_com1);
    if (state < 0) return state;
    if (state == 1) return process_error_busy;
    if (state == 2) {
        const i64 reset = sdk::pio_grant(pio_grant_action::recover, 0, pio_resource_com1);
        if (reset != 0) return reset;
    } else if (state != 0) return process_error_state;
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
    if (result < 0 && result != thread_error_timeout) current_mode = mode::unavailable;
    return result == thread_error_timeout ? 0 : result;
}

extern "C" i64 xos_console_write_hook(u32 handle, const void* data, u64 length) {
    if (current_mode == mode::legacy)
        return sdk::syscall(sys_handle_write, handle, reinterpret_cast<u64>(data), length);
    if (current_mode != mode::active) return process_error_state;
    if (data == nullptr && length != 0) return process_error_invalid;
    const auto* bytes = static_cast<const u8*>(data);
    u64 done = 0;
    while (done < length && done < 0x7fffffffffffffffull) {
        const u64 remaining = length - done < 0x7fffffffffffffffull - done
            ? length - done : 0x7fffffffffffffffull - done;
        const u32 amount = remaining > terminal::data_bytes ? terminal::data_bytes : static_cast<u32>(remaining);
        const i64 result = terminal::write_until(session, bytes + done, amount, thread_deadline_infinite);
        if (result <= 0 || result > amount) {
            current_mode = mode::unavailable;
            return done != 0 ? static_cast<i64>(done) : result < 0 ? result : process_error_state;
        }
        done += static_cast<u64>(result);
    }
    return static_cast<i64>(done);
}
}
