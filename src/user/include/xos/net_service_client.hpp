// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/net_service_abi.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

namespace xos::net2 {
class session_client {
public:
    session_client() = default;
    session_client(const session_client&) = delete;
    session_client& operator=(const session_client&) = delete;
    ~session_client() { close(); }
    i64 connect(u64 expected_service_pid) {
        if (!expected_service_pid) return invalid;
        if (channel_.send) return resources;
        const i64 result = sdk::ipc_name_connect(service_name, channel_);
        if (result) { close(); return closed; }
        u64 send_peer = 0, receive_peer = 0;
        if (sdk::ipc_endpoint_peer(channel_.send, send_peer) || sdk::ipc_endpoint_peer(channel_.receive, receive_peer) ||
            send_peer != expected_service_pid || receive_peer != expected_service_pid) {
            close(); return denied;
        }
        return 0;
    }
    void close() {
        if (channel_.send) (void)sdk::ipc_channel_close(channel_.send);
        if (channel_.receive) (void)sdk::ipc_channel_close(channel_.receive);
        channel_ = {}; next_sequence_ = 1;
    }
    i64 request(message& input, message& reply) {
        reply = {};
        if (!channel_.send || !next_sequence_ || input.length > payload_bytes || input.reserved || input.result) return invalid;
        const i64 began = sdk::syscall(sys_clock_monotonic);
        if (began < 0) { close(); return io; }
        if (input.deadline <= static_cast<u64>(began) || input.deadline - static_cast<u64>(began) > max_request_ns) {
            close(); return timeout;
        }
        input.version = version; input.sequence = next_sequence_++;
        bool sent = false;
        for (;;) {
            const i64 clock = sdk::syscall(sys_clock_monotonic);
            if (clock < 0) { close(); return io; }
            const u64 now = static_cast<u64>(clock);
            if (now >= input.deadline) { close(); return timeout; }
            if (!sent) {
                const i64 result = sdk::ipc_send(channel_.send, &input, header_bytes + input.length);
                if (!result) sent = true;
                else if (result != ipc_error_full) { close(); return closed; }
            }
            if (sent) {
                const i64 received = sdk::ipc_recv(channel_.receive, &reply, sizeof(reply));
                if (received != -3) {
                    if (received < header_bytes || reply.version != version || reply.action != input.action ||
                        reply.sequence != input.sequence || reply.deadline || reply.reserved || reply.address ||
                        reply.port || reply.transport != protocol::none || reply.length > payload_bytes ||
                        static_cast<u64>(received) != header_bytes + reply.length ||
                        (reply.result < 0 && reply.length) ||
                        (input.action != operation::open && reply.object != input.object) ||
                        (input.action == operation::open && ((reply.result == 0) != (reply.object != 0))) ||
                        (reply.result > 0 && (input.action != operation::send || static_cast<u64>(reply.result) > input.length))) {
                        reply = {}; close(); return io;
                    }
                    return reply.result;
                }
            }
            const u64 next = input.deadline - now < thread_tick_ns ? input.deadline : now + thread_tick_ns;
            if (sdk::syscall(sys_sleep_until, next)) { close(); return io; }
        }
    }
private:
    ipc_channel channel_{};
    u64 next_sequence_ = 1;
};
}
