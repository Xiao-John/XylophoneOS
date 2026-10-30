// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/terminal_abi.hpp>

namespace xos::terminal {
// A single-owner application client; callers serialize access. Identities are
// expected values supplied by the trusted launcher and verified by the kernel.
struct client {
    u32 send_handle = 0, receive_handle = 0;
    u64 controller_pid = 0, service_pid = 0, next_sequence = 1;
};
i64 connect(client& session, u64 controller_pid, u64 service_pid);
i64 read_until(client& session, void* data, u32 length, u64 deadline_ns);
i64 write_until(client& session, const void* data, u32 length, u64 deadline_ns);
void close(client& session);
}
