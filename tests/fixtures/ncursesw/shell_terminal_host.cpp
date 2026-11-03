// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/terminal_control.hpp>
#include <xos/thread_abi.hpp>
#include "../../../src/user/services/shell_terminal.hpp"

using namespace xos;
namespace {
u32 raw_calls = 0, length_seen = 0;
u64 deadline_seen = 0;
bool timeout = false, fail_start = false, fail_detach = false;
bool recovery_test = false, completion_ready = false;
u32 recover_calls = 0;
}
namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64, u64) {
    if (number == sys_clock_monotonic) return 100;
    if (recovery_test && number == sys_process_wait)
        return completion_ready ? 0 : process_error_would_block;
    if (recovery_test && number == sys_pio_grant) {
        if (first == static_cast<u64>(pio_grant_action::query)) return 2;
        if (first == static_cast<u64>(pio_grant_action::recover)) { ++recover_calls; return 0; }
    }
    ++raw_calls;
    return 7;
}
}
namespace xos::terminal {
i64 start(control& value, const char*) {
    if (fail_start) return process_error_state;
    value.child = 1; return 1;
}
i64 read_until(control&, void*, u32 length, u64 deadline) {
    length_seen = length; deadline_seen = deadline;
    return timeout ? thread_error_timeout : 1;
}
i64 write_until(control&, const void*, u32 length, u64 deadline) {
    length_seen = length; deadline_seen = deadline; return length > 0 ? 1 : 0;
}
i64 attach(control&, application& app, u64 child) {
    if (child == 0) return process_error_invalid;
    app.incoming = 12; app.outgoing = 13; app.peer = child; return 0;
}
i64 detach(control&, application& app) {
    app = {};
    return fail_detach ? process_error_state : 0;
}
i64 exchange(control&, request&, response&) { return process_error_state; }
void close(control& session) { session = {}; }
}
int main(int argc, char**) {
    char buffer[300]{};
    if (argc > 1) {
        fail_start = true;
        if (user::shell_terminal::start("/terminal") != process_error_state ||
            sdk::read(0, buffer, 1) != process_error_state || raw_calls != 0) return 7;
        return 0;
    }
    if (sdk::write(1, buffer, sizeof(buffer)) != 7 || sdk::read(0, buffer, 1) != 7 || raw_calls != 2)
        return 1;
    if (user::shell_terminal::start("/terminal") != 1) return 2;
    if (sdk::write(1, buffer, sizeof(buffer)) != static_cast<i64>(sizeof(buffer)) || length_seen != 1 ||
        deadline_seen != thread_deadline_infinite) return 3;
    timeout = true;
    if (sdk::read(0, buffer, 1) != 0 || deadline_seen != 100 + thread_tick_ns) return 4;
    if (sdk::write(3, buffer, 1) != 7 || raw_calls != 3) return 5;
    if (user::shell_terminal::start("/terminal") != process_error_state) return 6;
    if (user::shell_terminal::prepare_application(42, nullptr) != 0 ||
        *user::shell_terminal::application_send_handle() != 12 ||
        user::shell_terminal::prepare_application(43, nullptr) != process_error_state ||
        user::shell_terminal::finish_application() != 0 ||
        *user::shell_terminal::application_send_handle() != 0) return 8;
    if (user::shell_terminal::prepare_application(44, nullptr) != 0) return 9;
    fail_detach = true;
    if (user::shell_terminal::finish_application() != process_error_state ||
        sdk::read(0, buffer, 1) != process_error_state) return 10;
    recovery_test = true;
    if (user::shell_terminal::recover("/terminal") != process_error_would_block || recover_calls != 0) return 11;
    completion_ready = true;
    if (user::shell_terminal::recover("/terminal") != 1 || recover_calls != 1 ||
        sdk::write(1, buffer, 1) != 1) return 12;
    return 0;
}
