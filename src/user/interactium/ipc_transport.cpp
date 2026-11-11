// SPDX-License-Identifier: Apache-2.0
#include "ipc_transport.hpp"
#include <xos/sdk.hpp>

namespace xos::interactium {

u64 ipc_session_transport::authenticated_owner() const {
    u64 peer = 0;
    return sdk::ipc_endpoint_peer(channel_.receive, peer) == 0 ? peer : 0;
}

i32 ipc_session_transport::receive(u8* buffer, u32 capacity, u32& size) {
    size = 0;
    const i64 ready = sdk::ipc_wait(channel_.receive, ipc_wait_mode::try_receive);
    if (ready == process_error_would_block) return transport_again;
    if (ready < 0) return transport_closed;
    const i64 received = sdk::ipc_recv(channel_.receive, buffer, capacity);
    if (received == process_error_would_block) return transport_again;
    if (received < 0 || static_cast<u64>(received) > capacity) return transport_closed;
    size = static_cast<u32>(received);
    return static_cast<i32>(received);
}

i32 ipc_session_transport::send(const u8* buffer, u32 size) {
    if (size == 0) return transport_closed;
    const i64 ready = sdk::ipc_wait(channel_.send, ipc_wait_mode::try_send);
    if (ready == process_error_would_block) return transport_again;
    if (ready < 0) return transport_closed;
    const i64 sent = sdk::ipc_send(channel_.send, buffer, size);
    return sent == 0 ? static_cast<i32>(size) : transport_closed;
}

bool ipc_session_transport::closed() const {
    u64 peer = 0;
    return sdk::ipc_endpoint_peer(channel_.receive, peer) != 0 || peer == 0;
}

bool ipc_session_transport::reply_drained() const {
    return sdk::ipc_wait(channel_.send, ipc_wait_mode::try_send) == 0;
}

void ipc_session_transport::close() {
    if (channel_.send != 0) (void)sdk::ipc_channel_close(channel_.send);
    channel_ = {};
}

} // namespace xos::interactium
