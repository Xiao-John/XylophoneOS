// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/terminal_control.hpp>
#include <xos/thread_abi.hpp>
#include "../../../src/user/services/shell_terminal.hpp"

using namespace xos;
namespace {
u32 raw_calls = 0, length_seen = 0;
u64 deadline_seen = 0;
bool timeout = false, fail_start = false;
}
namespace xos::sdk {
i64 syscall(u64 number, u64, u64, u64) {
    if (number == sys_clock_monotonic) return 100;
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
    if (sdk::write(1, buffer, sizeof(buffer)) != 1 || length_seen != terminal::data_bytes ||
        deadline_seen != thread_deadline_infinite) return 3;
    timeout = true;
    if (sdk::read(0, buffer, 1) != 0 || deadline_seen != 100 + thread_tick_ns) return 4;
    if (sdk::write(3, buffer, 1) != 7 || raw_calls != 3) return 5;
    if (user::shell_terminal::start("/terminal") != process_error_state) return 6;
    return 0;
}
