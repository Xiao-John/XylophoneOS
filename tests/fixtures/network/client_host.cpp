// SPDX-License-Identifier: Apache-2.0
#include <xos/net_service_client.hpp>
#include <cassert>
#include <cstdio>
#include <cstring>

namespace {
xos::i64 clock_value = 100;
xos::u64 authenticated_peer = 42;
bool mismatched_receive_peer = false, no_reply = false, malformed = false;
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
        auto& response = *reinterpret_cast<message*>(second); response = {};
        response.version = version; response.action = last_request.action;
        response.sequence = last_request.sequence + (malformed ? 1 : 0); response.object = last_request.object;
        if (last_request.action == operation::send) response.result = last_request.length;
        return header_bytes;
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
    clock_value = -1; assert(client.request(request, reply) == io);
    std::puts("PASS N2 SDK: pinned peers, exact responses, pre-send deadlines, no replay after delivery, reconnect sequence, clock failure");
}
