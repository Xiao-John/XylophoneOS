// SPDX-License-Identifier: Apache-2.0
#include "resource_bridge.hpp"

namespace xos::user::pumpkin {
namespace {
constexpr u64 ticket_lifetime_ns = 2'000'000'000ull;
}

resource_bridge::~resource_bridge() { close(); }

void resource_bridge::close() {
    close_ipc(broker_);
    peer_ = 0;
    sequence_ = 0;
    reply_deadline_ = 0;
    for (auto& read : reads_) { read = {}; }
}

status resource_bridge::invoke(service_core& core, const connection_id& connection,
                               const ipc_channel& channel, bool registrar, const wire_request& request,
                               u64 now, wire_reply& reply) {
    if (request.operation == wire_operation::admit_resource_broker) {
        if (!registrar || peer_) { return status::denied; }
        resource_broker_grant grant{};
        __builtin_memcpy(&grant, request.name, sizeof(grant));
        const ipc_channel pair{grant.send, grant.receive};
        if (!grant.peer || authenticated_peer(pair) != grant.peer ||
            grant.send == channel.send || grant.send == channel.receive ||
            grant.receive == channel.send || grant.receive == channel.receive ||
            sdk::ipc_wait(pair.send, ipc_wait_mode::try_send) != 0 ||
            sdk::ipc_wait(pair.receive, ipc_wait_mode::try_receive) != process_error_would_block) {
            return status::denied;
        }
        broker_ = pair;
        peer_ = grant.peer;
        return status::ok;
    }

    if (registrar || !peer_ || authenticated_peer(broker_) != peer_) { return status::denied; }
    u64 broker_connection = 0;
    __builtin_memcpy(&broker_connection, request.name, sizeof(broker_connection));
    const session_id session{request.token.scope, request.token.number};
    const u64 peer = authenticated_peer(channel);
    identity_id identity{};
    if (!peer || !broker_connection ||
        core.session_identity(connection, now, session, identity) != status::ok) {
        return status::denied;
    }
    pending_read* free = nullptr;
    for (auto& read : reads_) {
        if (read.ticket.number && read.origin == connection) {
            free = &read;
            break;
        }
        if (!free && (!read.ticket.number || read.expires <= now)) { free = &read; }
    }
    if (!free || next_ticket_ == ~u64{0} || now > ~u64{0} - ticket_lifetime_ns) {
        return status::exhausted;
    }
    nonce random{};
    if (sdk::syscall(sys_random_bytes, reinterpret_cast<u64>(random.bytes), sizeof(random.bytes)) != 0 ||
        random == nonce{}) {
        return status::unavailable;
    }
    reply.token = {random, ++next_ticket_};
    *free = {reply.token, connection, channel, session, peer, broker_connection, now + ticket_lifetime_ns};
    return status::ok;
}

status resource_bridge::authorize(service_core& core, const broker_read_request& request, u64 now) {
    for (auto& pending : reads_) {
        if (pending.ticket.number != request.ticket.number || pending.ticket.scope != request.ticket.scope) {
            continue;
        }
        if (!pending.ticket.number || pending.expires <= now ||
            pending.origin.incarnation != request.incarnation || pending.peer != request.peer ||
            pending.broker_connection != request.broker_connection ||
            authenticated_peer(pending.channel) != pending.peer) {
            return status::denied;
        }
        const auto read = pending;
        pending = {};
        return core.authorize_owner(read.origin, now, read.session,
            {read.origin, request.object, resource_read}, {request.object, request.owner, resource_read}, resource_read);
    }
    return status::denied;
}

void resource_bridge::poll(service_core& core, u64& now) {
    if (!peer_) { return; }
    if (authenticated_peer(broker_) != peer_) { close(); return; }
    for (auto& read : reads_) {
        if (read.ticket.number && read.expires <= now) { read = {}; }
    }
    const auto ready = sdk::ipc_wait(broker_.send, ipc_wait_mode::try_send);
    if (ready == process_error_would_block && reply_deadline_ && now < reply_deadline_) { return; }
    if (ready != 0) { close(); return; }
    reply_deadline_ = 0;
    broker_read_request request{};
    const auto received = sdk::ipc_recv(broker_.receive, &request, sizeof(request));
    if (received == process_error_would_block) { return; }
    if (received != sizeof(request) || request.version != wire_version || request.reserved ||
        request.sequence == 0 || request.sequence != sequence_ + 1 || !request.peer ||
        !request.broker_connection || !request.object.number || !request.object.generation ||
        request.object.registry == nonce{} || !request.owner.number || request.owner.realm == nonce{}) {
        close();
        return;
    }
    sequence_ = request.sequence;
    const auto observed = monotonic_now();
    if (observed < 0 || static_cast<u64>(observed) < now) { close(); return; }
    now = static_cast<u64>(observed);
    broker_read_reply reply{wire_version, wire_status::denied, sequence_};
    if (request.deadline > now && request.deadline - now <= max_request_ns &&
        authorize(core, request, now) == status::ok) {
        reply.result = wire_status::ok;
    }
    if (sdk::ipc_send(broker_.send, &reply, sizeof(reply)) != 0) { close(); return; }
    const auto sent = monotonic_now();
    if (sent < 0 || static_cast<u64>(sent) < now) { close(); return; }
    now = static_cast<u64>(sent);
    reply_deadline_ = now + reply_budget_ns;
}

bool broker_authority::bind(ipc_channel channel, u64 expected_peer) {
    if (peer_ || !expected_peer || authenticated_peer(channel) != expected_peer) {
        close_ipc(channel);
        return false;
    }
    channel_ = channel;
    peer_ = expected_peer;
    return true;
}

status broker_authority::authorize(broker_read_request& request) {
    const auto now = monotonic_now();
    if (!live() || sequence_ == ~u64{0} || now < 0 ||
        request.deadline <= static_cast<u64>(now) || request.deadline - static_cast<u64>(now) > max_request_ns) {
        return status::unavailable;
    }
    // The client's authorization deadline travels with the request. Once
    // submitted, the shared pair must still consume its matching reply under
    // a broker-owned budget before it can serve another client.
    const auto transport_deadline = static_cast<u64>(now) + max_request_ns;
    request.sequence = ++sequence_;
    if (sdk::ipc_send(channel_.send, &request, sizeof(request)) == 0) {
        for (;;) {
            broker_read_reply reply{};
            const auto arrived = sdk::ipc_recv(channel_.receive, &reply, sizeof(reply));
            const auto clock = monotonic_now();
            if (clock < now || static_cast<u64>(clock) >= transport_deadline) { break; }
            if (arrived == sizeof(reply) && reply.version == wire_version && reply.sequence == request.sequence) {
                if (reply.result == wire_status::ok || reply.result == wire_status::denied) {
                    if (static_cast<u64>(clock) >= request.deadline) { return status::unavailable; }
                    return reply.result == wire_status::ok ? status::ok : status::denied;
                }
            }
            if (arrived != process_error_would_block || !sleep_tick(static_cast<u64>(clock))) { break; }
        }
    }
    close_ipc(channel_);
    return status::unavailable;
}

}
