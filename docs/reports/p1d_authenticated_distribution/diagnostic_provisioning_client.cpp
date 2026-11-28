#include <cstdio>
// SPDX-License-Identifier: Apache-2.0
#include "native_ipc.hpp"
#include "provisioning_protocol.hpp"

namespace xos::user::pumpkin {
exchange ipc_client::call(provisioning_request& request, provisioning_reply& reply) {
    reply = {};
    const auto start = monotonic_now();
    if (!channel_.send || sequence_ == ~u64{0} || start < 0 ||
        static_cast<u64>(start) > ~u64{0} - max_request_ns) {
        std::fprintf(stderr,"P1D_IPC_DIAG preflight op=%u send=%u receive=%u sequence=%llu now=%lld\n",
            static_cast<unsigned>(request.operation), channel_.send, channel_.receive,
            static_cast<unsigned long long>(sequence_), static_cast<long long>(start));
        close(); return exchange::not_sent; }
    request.sequence = ++sequence_; request.deadline = static_cast<u64>(start) + max_request_ns;
    const auto sent = sdk::ipc_send(channel_.send, &request, sizeof(request));
    if (sent != 0) {
        u64 peer = 0;
        const auto queried = sdk::ipc_endpoint_peer(channel_.send, peer);
        const auto writable = sdk::ipc_wait(channel_.send, ipc_wait_mode::try_send);
        std::fprintf(stderr,"P1D_IPC_DIAG op=%u send=%u receive=%u sequence=%llu now=%lld sent=%lld peer_result=%lld peer=%llu writable=%lld\n",
            static_cast<unsigned>(request.operation), channel_.send, channel_.receive,
            static_cast<unsigned long long>(request.sequence), static_cast<long long>(start),
            static_cast<long long>(sent), static_cast<long long>(queried),
            static_cast<unsigned long long>(peer), static_cast<long long>(writable));
        close(); return exchange::not_sent;
    }
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
