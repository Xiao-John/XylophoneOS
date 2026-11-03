// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/terminal_abi.hpp>

namespace xos::terminal {
// Supervisor-only provisional control client. Calls must be serialized.
// A failed exchange invalidates the channels; if the request was sent, its
// outcome can be unknown. The child remains available for the caller to reap.
struct control {
    u32 send_handle = 0, receive_handle = 0;
    u64 child = 0, next_sequence = 1, next_response = 1;
    u32 outstanding = 0;
};
struct application { u32 incoming = 0, outgoing = 0; u64 peer = 0; };
i64 start(control& session, const char* path);
// At most two requests may be outstanding, answered in order. A request arriving during
// read_until interrupts that read; its response precedes the new response.
i64 submit(control& session, request& message);
i64 receive(control& session, response& reply);
i64 exchange(control& session, request& message, response& reply);
i64 read_until(control& session, void* data, u32 length, u64 deadline_ns);
i64 write_until(control& session, const void* data, u32 length, u64 deadline_ns);
// Caller owns cleanup if child construction subsequently fails.
i64 attach(control& session, application& app, u64 child);
i64 detach(control& session, application& app);
void close(application& app);
void close(control& session);
}
