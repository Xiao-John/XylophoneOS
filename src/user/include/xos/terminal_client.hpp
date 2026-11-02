// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/terminal_abi.hpp>
#include <xos/spawn.hpp>

namespace xos::terminal {
// A single-owner application client; callers serialize access. Identities are
// expected values supplied by the trusted launcher and verified by the kernel.
struct client {
    u32 send_handle = 0, receive_handle = 0;
    u64 controller_pid = 0, service_pid = 0, next_sequence = 1;
};
i64 connect(client& session, u64 controller_pid, u64 service_pid);
i64 connect_startup(client& session, const startup_info* startup);
// Register a kernel-derived pair before committing the corresponding fork.
// On any error the caller must abort the unstarted child; transport failure
// may mean the service already processed the request.
i64 register_fork(client& session, const channel_fork_pair& pair);
i64 get_mode(client& session, mode& value);
i64 set_mode(client& session, const mode& value, mode_action action = mode_action::now);
i64 drain(client& session);
i64 flush_input(client& session);
// May return zero for an empty nonblocking/timed read, not EOF.
i64 read_mode(client& session, void* data, u32 length);
i64 read_until(client& session, void* data, u32 length, u64 deadline_ns);
i64 wait_readable(client& session, u64 deadline_ns);
i64 write_until(client& session, const void* data, u32 length, u64 deadline_ns);
void close(client& session);
}
