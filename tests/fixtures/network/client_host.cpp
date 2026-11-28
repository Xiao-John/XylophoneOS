// SPDX-License-Identifier: Apache-2.0
#include <xos/net_service_client.hpp>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>

namespace {
xos::i64 clock_value = 100;
xos::u64 authenticated_peer = 42;
bool mismatched_receive_peer = false, no_reply = false, malformed = false;
bool old_server = false;
unsigned snapshot_mutation = 0;
xos::i64 transport_error = 0;
unsigned send_count, close_count;
xos::net2::message last_request;
}
namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    using namespace net2;
    if (number == sys_clock_monotonic) return clock_value;
    if (number == sys_sleep_until) { clock_value = static_cast<i64>(first); return 0; }
    if (number == sys_ipc_name && first == static_cast<u64>(ipc_name_action::connect)) {
        *reinterpret_cast<ipc_channel*>(third) = {11, 12}; return 0;
    }
    if (number == sys_ipc_endpoint) {
        if (first == static_cast<u64>(ipc_endpoint_action::query_peer)) {
            *reinterpret_cast<u64*>(third) = authenticated_peer + (mismatched_receive_peer && second == 12 ? 1 : 0);
            return 0;
        }
        if (first == static_cast<u64>(ipc_endpoint_action::close)) { ++close_count; return 0; }
    }
    if (number == 4) {
        assert(first == 11 && third <= sizeof(last_request));
        std::memcpy(&last_request, reinterpret_cast<const void*>(second), static_cast<size_t>(third));
        ++send_count; return 0;
    }
    if (number == 5) {
        assert(first == 12 && third == sizeof(message));
        if (no_reply) return -3;
        if (transport_error) return transport_error;
        auto& response = *reinterpret_cast<message*>(second); response = {};
        response.version = version; response.action = last_request.action;
        response.sequence = last_request.sequence + (malformed ? 1 : 0); response.object = last_request.object;
        if (last_request.action == operation::send) response.result = last_request.length;
        if (last_request.action == operation::capabilities) {
            if (old_server) response.result = unsupported;
            else {
                const capability_snapshot snapshot{socket_extension_revision,
                    capability_readiness | capability_shutdown_write, snapshot_mutation ? 1u : 0u};
                response.length = sizeof(snapshot); std::memcpy(response.data, &snapshot, sizeof(snapshot));
            }
        }
        if (last_request.action == operation::readiness) {
            readiness_snapshot snapshot{1, ready_read | ready_write, 2, 37, 0, 0};
            if (snapshot_mutation == 1) snapshot.generation = 0;
            if (snapshot_mutation == 2) snapshot.reserved = 1;
            if (snapshot_mutation == 3) snapshot.events |= 128;
            if (snapshot_mutation == 4) snapshot.readable_bytes = tcp_receive_bytes + 1;
            if (snapshot_mutation == 5) snapshot.events &= ~ready_read;
            if (snapshot_mutation == 6) snapshot.writable_bytes = 0;
            if (snapshot_mutation == 7) snapshot.error = reset;
            if (snapshot_mutation == 8) snapshot.events |= ready_write_closed;
            response.length = sizeof(snapshot); std::memcpy(response.data, &snapshot, sizeof(snapshot));
        }
        if (last_request.action == operation::lease_status) {
            lease_snapshot value{lease_revision, 4, 0, 0, 2, 1, 10, 20, 30,
                permitted_address, static_address, static_mask, permitted_address, permitted_address, 2, 0, 0, 1, 0};
            if (snapshot_mutation == 1) value.revision = 2;
            if (snapshot_mutation == 2) value.epoch = 0;
            if (snapshot_mutation == 3) value.state = 9;
            if (snapshot_mutation == 4) value.reason = 8;
            if (snapshot_mutation == 5) value.reserved = 1;
            if (snapshot_mutation == 6) value.address = 0;
            if (snapshot_mutation == 7) value.t1 = value.t2;
            if (snapshot_mutation == 8) value.mask = 0xffff00ff;
            if (snapshot_mutation == 9) value.server = 0x7f000001;
            if (snapshot_mutation == 10) value.gateway = value.address;
            if (snapshot_mutation == 11) value.resolver = 0xffffffff;
            if (snapshot_mutation == 12) value.state = 1;
            if (snapshot_mutation == 13) value.start_attempts = 0;
            if (snapshot_mutation == 14) value.start_failures = 2;
            response.length = sizeof(value); std::memcpy(response.data, &value, sizeof(value));
        }
        return header_bytes + response.length;
    }
    assert(false); return -1;
}
}
int main() {
    using namespace xos;
    using namespace net2;
    session_client client;
    assert(client.connect(0) == invalid && !close_count);
    assert(client.connect(43) == denied && close_count == 2);
    mismatched_receive_peer = true;
    assert(client.connect(42) == denied); mismatched_receive_peer = false;
    assert(!client.connect(42));
    message request{}, reply{};
    request.action = operation::send; request.object = 77; request.length = 3;
    request.data[0] = 'a'; request.data[1] = 'b'; request.data[2] = 'c';
    request.deadline = u64(clock_value) + 1'000'000'000;
    assert(client.request(request, reply) == 3 && send_count == 1 && request.sequence == 1);
    malformed = true; assert(client.request(request, reply) == io && !reply.length);
    malformed = false; assert(!client.connect(42));
    request.deadline = u64(clock_value); unsigned before = send_count;
    assert(client.request(request, reply) == timeout && send_count == before);
    assert(!client.connect(42)); no_reply = true;
    request.deadline = u64(clock_value) + 20'000'000;
    assert(client.request(request, reply) == timeout && send_count == before + 1);
    no_reply = false; assert(!client.connect(42));
    request.deadline = u64(clock_value) + 20'000'000;
    assert(client.request(request, reply) == 3 && request.sequence == 1);
    capability_snapshot capabilities{};
    assert(client.capabilities(request.deadline, capabilities) == 0 &&
           capabilities.flags == (capability_readiness | capability_shutdown_write));
    readiness_snapshot readiness{};
    assert(client.readiness(77, request.deadline, readiness) == 0 && readiness.readable_bytes == 2);
    assert(client.shutdown_write(77, request.deadline) == 0);
    old_server = true;
    assert(client.capabilities(request.deadline, capabilities) == unsupported);
    assert(client.request(request, reply) == 3); // Unsupported probe preserves old operations.
    old_server = false;
    for (snapshot_mutation = 1; snapshot_mutation <= 8; ++snapshot_mutation) {
        assert(client.readiness(77, request.deadline, readiness) == io && !readiness.generation);
        assert(!client.connect(42));
    }
    snapshot_mutation = 1;
    assert(client.capabilities(request.deadline, capabilities) == io && !capabilities.revision);
    snapshot_mutation = 0; assert(!client.connect(42));
    lease_snapshot lease{};
    assert(!client.lease_status(request.deadline, lease) && lease.epoch == 2);
    for (snapshot_mutation = 1; snapshot_mutation <= 14; ++snapshot_mutation) {
        assert(client.lease_status(request.deadline, lease) == io && !lease.epoch);
        assert(!client.connect(42));
    }
    snapshot_mutation = 0;
    for (const i64 error : {i64(-1), i64(ipc_error_broken)}) {
        const auto sent_before = send_count; transport_error = error;
        assert(client.lease_status(request.deadline, lease) == closed && !lease.epoch && send_count == sent_before + 1);
        transport_error = 0; assert(!client.connect(42));
    }
    clock_value = -1; assert(client.request(request, reply) == io);
    std::puts("PASS N2 SDK: pinned peers, exact responses, pre-send deadlines, no replay after delivery, reconnect sequence, clock failure");
}
