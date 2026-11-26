// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "resource_broker.hpp"

namespace xos::user::pumpkin {

class broker_read_client {
public:
    broker_read_client() = default;
    broker_read_client(const broker_read_client&) = delete;
    broker_read_client& operator=(const broker_read_client&) = delete;
    ~broker_read_client() { close_ipc(pair_); }

    bool connect(u64 expected_peer) {
        if (!expected_peer || pair_.send) { return false; }
        const auto start = monotonic_now();
        if (start < 0) { return false; }
        const u64 end = static_cast<u64>(start) + max_request_ns;
        for (;;) {
            const auto connected = sdk::ipc_name_connect(broker_service_name, pair_);
            if (connected == 0) { break; }
            const auto now = monotonic_now();
            if (connected != ipc_error_name_not_found || now < 0 ||
                static_cast<u64>(now) >= end || !sleep_tick(static_cast<u64>(now))) { return false; }
        }
        broker_opened opened{};
        if (authenticated_peer(pair_) != expected_peer || !receive_broker_frame(pair_, opened, end) ||
            opened.version != broker_wire_version || opened.reserved || !opened.connection) {
            close_ipc(pair_);
            return false;
        }
        number_ = opened.connection;
        peer_ = expected_peer;
        return true;
    }

    u64 connection_number() const { return number_; }

    wire_status prepare(ipc_client& daemon, wire_id session, wire_id& ticket) const {
        ticket = {};
        if (!number_ || !peer_ || authenticated_peer(pair_) != peer_) { return wire_status::unavailable; }
        wire_request begin{};
        begin.operation = wire_operation::begin_resource_read;
        begin.token = session;
        begin.name_length = sizeof(number_);
        __builtin_memcpy(begin.name, &number_, sizeof(number_));
        wire_reply reply{};
        if (daemon.call(begin, reply) != exchange::received) { return wire_status::unavailable; }
        ticket = reply.token;
        return reply.result;
    }

    bool read(wire_id ticket, broker_data& output, const named_resource_request* named = nullptr) {
        output = {};
        const auto now = monotonic_now();
        if (now < 0 || !peer_ || authenticated_peer(pair_) != peer_ || !ticket.number || ticket.scope == nonce{}) {
            return false;
        }
        broker_read request{broker_wire_version, 0, named ? 0 : broker_object_number,
            static_cast<u64>(now) + max_request_ns, ticket};
        if (named) { request.named = *named; }
        broker_data reply{};
        const bool received = sdk::ipc_send(pair_.send, &request, sizeof(request)) == 0 &&
            receive_broker_frame(pair_, reply, request.deadline);
        close_ipc(pair_);
        number_ = peer_ = 0;
        if (!received || reply.version != broker_wire_version || reply.reserved || reply.data.length > sealed_blob_capacity ||
            has_bytes(reply.data.bytes + reply.data.length, sizeof(reply.data.bytes) - reply.data.length)) { return false; }
        if (reply.result == wire_status::ok) {
            if (named ? reply.data.length != sizeof(u32) || !reply.generation ||
                        (named->generation && reply.generation != named->generation) :
                        !reply.data.length || reply.generation) { return false; }
        } else if ((reply.result != wire_status::denied && reply.result != wire_status::io_error &&
                    reply.result != wire_status::unavailable) || reply.data.length || reply.generation ||
                   has_bytes(reply.data.bytes, sizeof(reply.data.bytes))) { return false; }
        output = reply;
        return true;
    }

private:
    ipc_channel pair_{};
    u64 number_ = 0;
    u64 peer_ = 0;
};

}
