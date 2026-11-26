// SPDX-License-Identifier: Apache-2.0
#include "pumpkin/resource_broker_main.cpp"
#include <cassert>
#include <cstdio>
#include <cstring>

namespace {
constexpr ipc_channel authority_lane{1, 2};
constexpr ipc_channel client_lane{3, 4};
constexpr u64 authority_pid = 7, client_pid = 8;
constexpr u64 tick = loop_interval_ns;
constexpr u8 content[]{'d', 'a', 't', 'a'};

struct clocked_ipc {
    u64 now = tick;
    u64 reply_at = tick;
    u64 client_receive_at = tick;
    u64 last_sequence = 0;
    bool authority_open = true;
    bool pending = false;
    bool client_pending = false;
    u32 authorization_calls = 0;
    u32 client_replies = 0;
    u32 file_reads = 0;
    u64 forwarded_deadline = 0;
    broker_read client_request{};
    wire_status authorization_result = wire_status::ok;
} fixture;

constexpr wire_id example_ticket{{{1}}, 1};
}

i64 xos::sdk::syscall(u64 number, u64 first, u64 second, u64 third) {
    switch (number) {
    case sys_clock_monotonic:
        return static_cast<i64>(fixture.now);
    case sys_sleep_until:
        assert(first > fixture.now);
        fixture.now = first;
        return 0;
    case sys_ipc_endpoint: {
        const auto action = static_cast<ipc_endpoint_action>(first);
        if (action == ipc_endpoint_action::query_peer) {
            if (second == authority_lane.send || second == authority_lane.receive) {
                if (!fixture.authority_open) { return process_error_denied; }
                *reinterpret_cast<u64*>(third) = authority_pid;
            } else {
                assert(second == client_lane.send || second == client_lane.receive);
                *reinterpret_cast<u64*>(third) = client_pid;
            }
            return 0;
        }
        assert(action == ipc_endpoint_action::close);
        assert(second == authority_lane.send || second == authority_lane.receive);
        fixture.authority_open = false;
        return 0;
    }
    case 4: // sdk::ipc_send
        if (first == authority_lane.send) {
            assert(third == sizeof(broker_read_request) && fixture.authority_open && !fixture.pending);
            const auto& request = *reinterpret_cast<const broker_read_request*>(second);
            assert(request.sequence == fixture.last_sequence + 1);
            fixture.last_sequence = request.sequence;
            fixture.forwarded_deadline = request.deadline;
            fixture.pending = true;
            ++fixture.authorization_calls;
        } else {
            assert(first == client_lane.send && third == sizeof(broker_data));
            const auto& reply = *reinterpret_cast<const broker_data*>(second);
            assert(reply.result == wire_status::ok && reply.data.length == sizeof(content));
            assert(std::memcmp(reply.data.bytes, content, sizeof(content)) == 0);
            ++fixture.client_replies;
        }
        return 0;
    case 5: // sdk::ipc_recv
        if (first == authority_lane.receive) {
            assert(third == sizeof(broker_read_reply) && fixture.pending);
            if (fixture.now < fixture.reply_at) { return process_error_would_block; }
            auto& reply = *reinterpret_cast<broker_read_reply*>(second);
            reply = {wire_version, fixture.authorization_result, fixture.last_sequence};
            fixture.pending = false;
            return sizeof(reply);
        }
        assert(first == client_lane.receive && third == sizeof(broker_read) && fixture.client_pending);
        fixture.now = fixture.client_receive_at;
        *reinterpret_cast<broker_read*>(second) = fixture.client_request;
        fixture.client_pending = false;
        return sizeof(broker_read);
    default:
        assert(false);
        return -1;
    }
}

bool xos::file::client::init() { return true; }
i64 xos::file::client::anonymous(u32& handle) { handle = 1; return 0; }
i64 xos::file::client::write(u32 handle, const void* bytes, u32 length) {
    assert(handle == 1 && length == sizeof(content) && std::memcmp(bytes, content, length) == 0);
    return length;
}
i64 xos::file::client::seal_anonymous(u32 handle) { assert(handle == 1); return 0; }
i64 xos::file::client::close(u32 handle) { assert(handle == 1); return 0; }
i64 xos::file::client::read_at(u32 handle, void* bytes, u32 capacity, u64 offset) {
    assert(handle == 1 && capacity == sizeof(content) && offset == 0);
    std::memcpy(bytes, content, capacity);
    ++fixture.file_reads;
    return capacity;
}

int main() {
    file::client files;
    sealed_blob object(files);
    const nonce realm{{1}};
    assert(object.publish({realm, broker_object_number, 1}, realm, {realm, 1}, content, sizeof(content)) == status::ok);

    {
        broker_authority authority;
        assert(authority.bind(authority_lane, authority_pid));
        client_slot first{client_lane, 1, 8 * tick, false};
        fixture.client_pending = true;
        fixture.client_request = {wire_version, 0, broker_object_number, 3 * tick, example_ticket};
        fixture.reply_at = 4 * tick;
        assert(!process_read(first, object, authority, fixture.now));
        assert(authority.live() && fixture.authorization_calls == 1 && !fixture.pending &&
               !fixture.file_reads && !fixture.client_replies);

        client_slot second{client_lane, 2, 8 * tick, false};
        fixture.client_pending = true;
        fixture.client_receive_at = fixture.now;
        fixture.client_request.deadline = 9 * tick;
        fixture.client_request.ticket = {{{2}}, 2};
        assert(process_read(second, object, authority, fixture.now));
        assert(authority.live() && fixture.authorization_calls == 2 && fixture.last_sequence == 2 &&
               fixture.file_reads == 1 && fixture.client_replies == 1 && fixture.forwarded_deadline == 8 * tick);
        std::puts("PASS expired client reply is drained and a fresh authorized read retains the same channel");

        client_slot closing{client_lane, 3, 8 * tick, false};
        fixture.client_pending = true;
        fixture.client_receive_at = closing.expires;
        fixture.client_request.ticket = {{{3}}, 3};
        assert(!process_read(closing, object, authority, fixture.now));
        assert(authority.live() && fixture.authorization_calls == 2 &&
               fixture.file_reads == 1 && fixture.client_replies == 1);
        std::puts("PASS actual receive time closes an expired client before authorization or file access");
    }

    fixture = {};
    broker_authority unavailable;
    assert(unavailable.bind(authority_lane, authority_pid));
    broker_read_request request{};
    request.deadline = 2 * tick;
    fixture.reply_at = ~u64{0};
    assert(unavailable.authorize(request) == status::unavailable && !unavailable.live());
    assert(fixture.now >= tick + max_request_ns);
    std::puts("PASS a missing authority reply closes its channel at the independent transport deadline");
}
