// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "daemon_protocol.hpp"
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

namespace xos::user::pumpkin {

inline i64 monotonic_now() {
    return sdk::syscall(sys_clock_monotonic);
}
inline bool sleep_tick(u64 now) {
    return now <= ~u64{0} - loop_interval_ns && sdk::syscall(sys_sleep_until, now + loop_interval_ns) == 0;
}
inline void close_ipc(ipc_channel& channel) {
    if (channel.send != 0) {
        (void)sdk::ipc_channel_close(channel.send);
    }
    if (channel.receive != 0) {
        (void)sdk::ipc_channel_close(channel.receive);
    }
    channel = {};
}
inline u64 authenticated_peer(const ipc_channel& channel) {
    u64 expected = 0, peer = 0;
    if (channel.send == 0 || channel.receive == 0 || channel.send == channel.receive ||
        sdk::ipc_endpoint_peer(channel.send, expected) != 0 ||
        sdk::ipc_endpoint_peer(channel.receive, peer) != 0 || peer != expected) {
        return 0;
    }
    return peer;
}

struct control_message {
    u32 version = wire_version;
    u32 reserved = 0;
    ipc_channel channel;
    nonce realm;
};
static_assert(sizeof(control_message) == 32);

enum class exchange { received, not_sent, outcome_unknown };

class ipc_client {
public:
    ipc_client() = default;
    ipc_client(const ipc_client&) = delete;
    ipc_client& operator=(const ipc_client&) = delete;
    ~ipc_client() { close(); }

    bool bind(ipc_channel channel, u64 expected_peer);
    void close();
    // The caller controls credential lifetimes in request and reply.
    exchange call(wire_request& request, wire_reply& reply);

private:
    ipc_channel channel_{};
    u64 sequence_ = 0;
};

// Takes ownership of the control pair. The service stops on its loss.
struct backing_liveness {
    void* context = nullptr;
    bool (*live)(void*) = nullptr;
};
class login_resource;
int serve_native(const store_api& store, const nonce& realm, const entropy_api& entropy,
                 ipc_channel control, u64 controller, const char* service_name,
                 backing_liveness backing = {}, login_resource* resource = nullptr);

}
