// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/terminal_abi.hpp>

namespace xos::terminal {
// Supervisor-only provisional control client. Calls must be serialized.
struct control {
    u32 send_handle = 0, receive_handle = 0;
    u64 child = 0, next_sequence = 1;
};
i64 start(control& session, const char* path);
i64 exchange(control& session, request& message, response& reply);
void close(control& session);
}
