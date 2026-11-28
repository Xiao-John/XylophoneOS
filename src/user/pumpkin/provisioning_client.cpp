// SPDX-License-Identifier: Apache-2.0
#include "native_ipc.hpp"
#include "provisioning_protocol.hpp"

namespace xos::user::pumpkin {
exchange ipc_client::call(provisioning_request& request, provisioning_reply& reply) {
    reply = {};
    const auto start = monotonic_now();
    if (!channel_.send || sequence_ == ~u64{0} || start < 0 ||
        static_cast<u64>(start) > ~u64{0} - max_request_ns) { close(); return exchange::not_sent; }
    request.sequence = ++sequence_; request.deadline = static_cast<u64>(start) + max_request_ns;
    if (sdk::ipc_send(channel_.send, &request, sizeof(request)) != 0) { close(); return exchange::not_sent; }
    for (;;) {
        const auto received = sdk::ipc_recv(channel_.receive, &reply, sizeof(reply));
        if (received != process_error_would_block) {
            if (received == sizeof(reply) && reply.magic == provisioning_magic &&
                reply.version == provisioning_protocol_version && reply.operation == request.operation &&
                reply.sequence == request.sequence && reply.result <= status::outcome_unknown) { return exchange::received; }
            break;
        }
        const auto now = monotonic_now();
        if (now < 0 || static_cast<u64>(now) >= request.deadline || !sleep_tick(static_cast<u64>(now))) { break; }
    }
    reply = {}; close(); return exchange::outcome_unknown;
}
}
