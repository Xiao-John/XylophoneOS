// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "native_ipc.hpp"

namespace xos::user::pumpkin {

// Private, single-object, read-only service channel. The object record and
// client endpoint identity come from the trusted broker's current state.
struct broker_read_request {
    u32 version = wire_version;
    u32 reserved = 0;
    u64 sequence = 0;
    u64 deadline = 0;
    u64 peer = 0;
    u64 broker_connection = 0;
    wire_id ticket{};
    nonce incarnation{};
    resource_key object{};
    identity_id owner{};
};
struct broker_read_reply {
    u32 version = wire_version;
    wire_status result = wire_status::denied;
    u64 sequence = 0;
};
static_assert(sizeof(broker_read_request) == 136 && sizeof(broker_read_reply) == 16);

class resource_bridge {
public:
    resource_bridge() = default;
    resource_bridge(const resource_bridge&) = delete;
    resource_bridge& operator=(const resource_bridge&) = delete;
    ~resource_bridge();
    status invoke(service_core& core, const connection_id& connection, const ipc_channel& channel,
                  bool registrar, const wire_request& request, u64 now, wire_reply& reply);
    void poll(service_core& core, u64& now);
    void close();

private:
    struct pending_read {
        wire_id ticket{};
        connection_id origin{};
        ipc_channel channel{};
        session_id session{};
        u64 peer = 0;
        u64 broker_connection = 0;
        u64 expires = 0;
    };

    status authorize(service_core& core, const broker_read_request& request, u64 now);
    ipc_channel broker_{};
    u64 peer_ = 0;
    u64 sequence_ = 0;
    u64 reply_deadline_ = 0;
    u64 next_ticket_ = 0;
    pending_read reads_[client_limit]{};
};

// Serial broker-side transport. A submitted request without a verified reply
// invalidates the channel. No authorization decision reaches the application.
class broker_authority {
public:
    ~broker_authority() { close_ipc(channel_); }
    broker_authority() = default;
    broker_authority(const broker_authority&) = delete;
    broker_authority& operator=(const broker_authority&) = delete;
    bool bind(ipc_channel channel, u64 expected_peer);
    bool live() const { return peer_ && authenticated_peer(channel_) == peer_; }
    status authorize(broker_read_request& request);

private:
    ipc_channel channel_{};
    u64 peer_ = 0;
    u64 sequence_ = 0;
};

}
