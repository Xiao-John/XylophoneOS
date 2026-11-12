// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/net_abi.hpp>
#include <xos/device_abi.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

namespace xos::net {
class client {
public:
    i64 connect(u64 expected_service_pid = 0) {
        if (channel_.send) return device_busy;
        const i64 result = sdk::ipc_name_connect(service_name, channel_);
        if (result) return result;
        u64 peer = 0;
        const i64 authenticated = sdk::ipc_endpoint_peer(channel_.send, peer);
        if (authenticated || (expected_service_pid && peer != expected_service_pid)) {
            close(); return device_denied;
        }
        return 0;
    }
    void close() {
        if (channel_.send) (void)sdk::ipc_channel_close(channel_.send);
        if (channel_.receive) (void)sdk::ipc_channel_close(channel_.receive);
        channel_ = {};
    }
    i64 request(operation action, const u8* data, u32 length, message& reply, u64 deadline) {
        reply = {};
        if (!channel_.send || !next_sequence_ || length > frame_bytes || (length && !data)) return device_invalid;
        message request{}; request.version = version; request.action = action; request.sequence = next_sequence_++;
        request.length = length;
        for (u32 i = 0; i < length; ++i) request.data[i] = data[i];
        bool sent = false;
        for (;;) {
            if (!sent) {
                const i64 result = sdk::ipc_send(channel_.send, &request, header_bytes + length);
                if (result == 0) sent = true;
                else if (result != -4) { close(); return result; }
            }
            if (sent) {
                const i64 received = sdk::ipc_recv(channel_.receive, &reply, sizeof(reply));
                if (received != -3) {
                    if (received < header_bytes || reply.version != version || reply.sequence != request.sequence ||
                        reply.action != action || reply.reserved || reply.length > frame_bytes ||
                        static_cast<u64>(received) != header_bytes + reply.length) {
                        reply = {}; close(); return device_io;
                    }
                    return reply.result;
                }
            }
            const i64 now = sdk::syscall(sys_clock_monotonic);
            if (now < 0 || static_cast<u64>(now) >= deadline) { close(); return device_timeout; }
            const u64 next = deadline - static_cast<u64>(now) < thread_tick_ns ? deadline : static_cast<u64>(now) + thread_tick_ns;
            if (sdk::syscall(sys_sleep_until, next) != 0) { close(); return device_io; }
        }
    }
private:
    ipc_channel channel_{};
    u64 next_sequence_ = 1;
};
}
