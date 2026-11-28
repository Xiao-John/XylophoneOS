// SPDX-License-Identifier: Apache-2.0
#include "native_ipc.hpp"

namespace xos::user::pumpkin {

bool ipc_client::bind(ipc_channel channel, u64 expected_peer) {
    close();
    if (expected_peer == 0 || authenticated_peer(channel) != expected_peer) {
        close_ipc(channel);
        return false;
    }
    channel_ = channel;
    return true;
}

void ipc_client::close() {
    close_ipc(channel_);
    sequence_ = 0;
}

exchange ipc_client::call(wire_request& request, wire_reply& reply) {
    wipe_bytes(&reply, sizeof(reply));
    const i64 start = monotonic_now();
    if (!channel_.send || sequence_ == ~u64{0} || start < 0) {
        close();
        return exchange::not_sent;
    }
    request.sequence = ++sequence_;
    request.deadline = static_cast<u64>(start) + max_request_ns;
    if (sdk::ipc_send(channel_.send, &request, sizeof(request)) != 0) {
        close();
        return exchange::not_sent;
    }
    for (;;) {
        const auto received = sdk::ipc_recv(channel_.receive, &reply, sizeof(reply));
        if (received != process_error_would_block) {
            if (received == sizeof(reply) && valid_reply(request, reply)) {
                return exchange::received;
            }
            break;
        }
        const i64 now = monotonic_now();
        if (now < 0 || static_cast<u64>(now) >= request.deadline || !sleep_tick(static_cast<u64>(now))) {
            break;
        }
    }
    wipe_bytes(&reply, sizeof(reply));
    close();
    return exchange::outcome_unknown;
}

}
