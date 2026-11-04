// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

namespace xos::sdk {
// sys_send/sys_recv retain the original IPC error values. A wait can wake
// spuriously, so the data operation, rather than the wake, decides readiness.
inline constexpr i64 ipc_error_empty = -3, ipc_error_full = -4;
inline i64 channel_send_wait(u32 handle, const void* data, u64 length, u64 deadline) {
    for (;;) {
        const i64 ready = channel_wait(handle, deadline);
        if (ready != 0) return ready;
        const i64 sent = ipc_send(handle, data, length);
        if (sent != ipc_error_full) return sent;
    }
}
inline i64 channel_receive_wait(u32 handle, void* data, u64 length, u64 deadline) {
    for (;;) {
        const i64 ready = channel_wait(handle, deadline);
        if (ready != 0) return ready;
        const i64 received = ipc_recv(handle, data, length);
        if (received != ipc_error_empty) return received;
    }
}
}
