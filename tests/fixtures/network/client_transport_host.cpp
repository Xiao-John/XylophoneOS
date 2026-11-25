// SPDX-License-Identifier: Apache-2.0
// Production native client branches with a deterministic IPC syscall fixture.
// This checks client protocol/cleanup behavior; it is not a guest or lwIP gate.
#include <xos/net_transport.hpp>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <utility>
#include <vector>

#ifdef NDEBUG
#error "Client transport regression assertions must remain enabled"
#endif

namespace {
using namespace xos;
using namespace xos::net2;

enum class corruption { none, sequence, object };
struct reply_step {
    operation action;
    i64 result = 0;
    u32 flags = 0;
    u64 opened_handle = 701;
    std::vector<u8> payload;
    bool lost_reply = false;
    corruption corrupt = corruption::none;
    bool late_reply = false;
};

std::vector<reply_step> script;
std::vector<message> requests;
size_t next_step = 0;
bool pending = false, send_open = false, receive_open = false;
i64 clock_value = 1'000'000'000;
unsigned sleeps = 0, endpoint_closes = 0, groups = 0;

reply_step step(operation action, i64 result = 0, u32 flags = 0) {
    return {action, result, flags, 701, {}, false, corruption::none, false};
}
void scenario(std::vector<reply_step> steps) {
    assert(!send_open && !receive_open);
    script = std::move(steps);
    requests.clear();
    next_step = 0;
    pending = false;
    clock_value = 1'000'000'000;
    sleeps = endpoint_closes = 0;
}
u64 deadline() { return static_cast<u64>(clock_value) + 1'000'000'000; }
void exhausted() { assert(next_step == script.size()); }
void disconnected() {
    exhausted();
    assert(!send_open && !receive_open && endpoint_closes == 2 && !pending);
}
void connected_client(client& value) { assert(value.connect(42) == 0); }
u64 open_connection(client& value, protocol transport, u64 until) {
    u64 handle = 999;
    assert(value.open(transport, permitted_address, 9000, until, handle) == 0 && handle == 701);
    return handle;
}

void datagram_cases() {
    auto payload = step(operation::receive);
    payload.payload = {'a', 0, 'b', 'c', 'd'};
    scenario({step(operation::open, 0, connected), step(operation::send), step(operation::receive),
              step(operation::receive, buffer_too_small, 5), payload, step(operation::close)});
    {
        client value;
        connected_client(value);
        const auto until = deadline();
        const auto handle = open_connection(value, protocol::udp, until);
        assert(value.send_datagram(handle, nullptr, 0, until) == 0);
        u8 bytes[8];
        std::memset(bytes, 0xa5, sizeof(bytes));
        u32 required = 99;
        assert(value.receive_datagram(handle, bytes, sizeof(bytes), until, required) == 0 && required == 0);
        for (const auto byte : bytes) assert(byte == 0xa5);
        assert(value.receive_datagram(handle, bytes, 2, until, required) == buffer_too_small && required == 5);
        for (const auto byte : bytes) assert(byte == 0xa5);
        assert(value.receive_datagram(handle, bytes, sizeof(bytes), until, required) == 5 && required == 5);
        assert(std::memcmp(bytes, "a\0bcd", 5) == 0 && bytes[5] == 0xa5);
        assert(value.close_connection(handle, until) == 0);
        assert(requests[0].transport == protocol::udp && requests[1].length == 0);
        assert(requests[3].flags == 2 && requests[4].flags == sizeof(bytes));
        for (const auto& request : requests) assert(request.deadline == until);
        exhausted();
    }
    disconnected();
    ++groups;
}

void connection_progress_cases() {
    scenario({step(operation::open, 0, connecting), step(operation::status, 0, connecting),
              step(operation::status, 0, connected), step(operation::close)});
    {
        client value;
        connected_client(value);
        const auto until = deadline();
        const auto handle = open_connection(value, protocol::tcp, until);
        assert(sleeps == 2 && requests.size() == 3);
        assert(requests[1].object == handle && requests[2].object == handle);
        assert(value.close_connection(handle, until) == 0);
        for (const auto& request : requests) assert(request.deadline == until);
        exhausted();
    }
    disconnected();
    // The real stack reports failed on status errors; cancellation releases the
    // allocated candidate without changing the original reset result.
    scenario({step(operation::open, 0, connecting), step(operation::status, reset, failed),
              step(operation::cancel)});
    {
        client value;
        connected_client(value);
        u64 handle = 999;
        assert(value.open(protocol::tcp, permitted_address, 9000, deadline(), handle) == reset && handle == 0);
        assert(requests.size() == 3 && requests.back().action == operation::cancel && requests.back().object == 701);
        exhausted();
    }
    disconnected();
    ++groups;
}

void retry_and_timeout_cases() {
    scenario({step(operation::open, 0, connected), step(operation::send, would_block), step(operation::send, 3),
              step(operation::close)});
    {
        client value;
        connected_client(value);
        const auto until = deadline();
        const auto handle = open_connection(value, protocol::tcp, until);
        const u8 bytes[]{'a', 0, 'b', 'c', 'd'};
        assert(value.write(handle, bytes, sizeof(bytes), until) == 3);
        assert(sleeps == 1 && requests.size() == 3);
        assert(requests[1].sequence + 1 == requests[2].sequence);
        for (size_t i = 1; i < requests.size(); ++i) {
            assert(requests[i].length == sizeof(bytes) && requests[i].deadline == until);
            assert(std::memcmp(requests[i].data, bytes, sizeof(bytes)) == 0);
        }
        assert(value.close_connection(handle, until) == 0);
        exhausted();
    }
    disconnected();

    auto dropped = step(operation::send);
    dropped.lost_reply = true;
    scenario({step(operation::open, 0, connected), dropped});
    {
        client value;
        connected_client(value);
        const auto until = static_cast<u64>(clock_value) + 2 * thread_tick_ns;
        const auto handle = open_connection(value, protocol::tcp, until);
        const u8 bytes[]{'u', 'n', 'c', 'e', 'r', 't', 'a', 'i', 'n'};
        assert(value.write(handle, bytes, sizeof(bytes), until) == timeout);
        assert(requests.size() == 2 && sleeps == 2);
        disconnected();
        // An accepted send with a lost reply must not be replayed on this or
        // any automatic replacement session. The caller must reconnect itself.
        assert(value.write(handle, bytes, sizeof(bytes), deadline()) == invalid);
        assert(requests.size() == 2 && endpoint_closes == 2);
    }
    disconnected();
    // A ready reply can cross the deadline during scheduling inside recv.
    // Its accepted send must still report timeout and must never be replayed.
    auto late = step(operation::send, 3); late.late_reply = true;
    scenario({step(operation::open, 0, connected), late});
    {
        client value; connected_client(value);
        const auto until = deadline();
        const auto handle = open_connection(value, protocol::tcp, until);
        const u8 bytes[]{'l', 'a', 't'};
        assert(value.write(handle, bytes, sizeof(bytes), until) == timeout);
        assert(requests.size() == 2 && sleeps == 0);
        disconnected();
    }
    disconnected();
    ++groups;
}

void receive_and_datagram_rejection_cases() {
    // TCP data may carry EOF together; the following read returns zero/EOF.
    auto final_data = step(operation::receive, 0, eof);
    final_data.payload = {'x', 'y'};
    scenario({step(operation::open, 0, connected), final_data, step(operation::receive, 0, eof),
              step(operation::close)});
    {
        client value;
        connected_client(value);
        const auto until = deadline();
        const auto handle = open_connection(value, protocol::tcp, until);
        u8 bytes[4]{};
        assert(value.read(handle, bytes, sizeof(bytes), until) == 2 && bytes[0] == 'x' && bytes[1] == 'y');
        assert(value.read(handle, bytes, sizeof(bytes), until) == 0);
        assert(value.close_connection(handle, until) == 0);
    }
    disconnected();

    for (unsigned kind = 0; kind < 5; ++kind) {
        auto response = step(operation::receive);
        const bool datagram = kind >= 2;
        if (kind == 1) response.payload = {'a', 'b', 'c'};
        if (kind == 2) response.flags = eof;
        if (kind >= 3) {
            response.result = buffer_too_small;
            response.flags = kind == 3 ? 2 : payload_bytes + 1;
        }
        scenario({step(operation::open, 0, connected), response});
        {
            client value;
            connected_client(value);
            const auto until = deadline();
            const auto handle = open_connection(value, datagram ? protocol::udp : protocol::tcp, until);
            u8 bytes[2]{0xa5, 0xa5};
            u32 required = 99;
            const auto result = datagram ? value.receive_datagram(handle, bytes, sizeof(bytes), until, required)
                                         : value.read(handle, bytes, sizeof(bytes), until);
            assert(result == io && bytes[0] == 0xa5 && bytes[1] == 0xa5);
            if (datagram) assert(required == 0);
            disconnected();
        }
        disconnected();
    }
    scenario({step(operation::open, 0, connected), step(operation::send, 1)});
    {
        client value;
        connected_client(value);
        const auto until = deadline();
        const auto handle = open_connection(value, protocol::udp, until);
        const u8 bytes[]{'a', 'b'};
        assert(value.send_datagram(handle, bytes, sizeof(bytes), until) == io);
        disconnected();
    }
    disconnected();
    ++groups;
}

void malformed_envelope_cases() {
    for (unsigned kind = 0; kind < 3; ++kind) {
        auto response = step(operation::open, 0, connected);
        if (kind == 0) response.corrupt = corruption::sequence;
        if (kind == 1) response.flags = connected | connecting;
        if (kind == 2) response.flags = eof;
        scenario({response});
        {
            client value;
            connected_client(value);
            u64 handle = 99;
            assert(value.open(protocol::tcp, permitted_address, 9000, deadline(), handle) == io && handle == 0);
            disconnected();
        }
        disconnected();
    }
    auto bad_object = step(operation::receive, 0, eof);
    bad_object.corrupt = corruption::object;
    scenario({step(operation::open, 0, connected), bad_object});
    {
        client value;
        connected_client(value);
        const auto until = deadline();
        const auto handle = open_connection(value, protocol::tcp, until);
        u8 byte = 0xa5;
        assert(value.read(handle, &byte, 1, until) == io && byte == 0xa5);
        disconnected();
    }
    disconnected();
    ++groups;
}

void strict_reply_shapes() {
    // Validate the actual information record shape, not an invented payload.
    auto information_reply = step(operation::information);
    information_reply.payload.resize(sizeof(information));
    scenario({information_reply});
    {
        session_client value;
        assert(value.connect(42) == 0);
        message request{}, reply{};
        request.action = operation::information;
        request.deadline = deadline();
        assert(value.request(request, reply) == 0 && reply.length == sizeof(information) && reply.flags == 0);
    }
    disconnected();

    // These are semantically valid envelope shapes but invalid operation
    // replies; production must close the session instead of ignoring fields.
    for (const auto action : {operation::open, operation::status, operation::send, operation::close,
                              operation::cancel, operation::revoke_peer, operation::stop, operation::information}) {
        for (unsigned malformed = 0; malformed < 2; ++malformed) {
            auto response = step(action);
            if (action == operation::open || action == operation::status) response.flags = connected;
            if (action == operation::send) response.result = 1;
            if (action == operation::information) response.payload.resize(sizeof(information));
            if (malformed == 0) response.payload.push_back(0x61);
            else response.flags |= 0x80000000u;
            scenario({response});
            {
                session_client value;
                assert(value.connect(42) == 0);
                message request{}, reply{};
                request.action = action;
                request.deadline = deadline();
                if (action != operation::open && action != operation::information && action != operation::stop)
                    request.object = 701;
                if (action == operation::send) { request.length = 1; request.data[0] = 0x61; }
                if (action == operation::open) {
                    request.address = permitted_address;
                    request.port = 9000;
                    request.transport = protocol::tcp;
                }
                assert(value.request(request, reply) == io);
                disconnected();
            }
            disconnected();
        }
    }
    ++groups;
}
}

namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    using namespace net2;
    if (number == sys_clock_monotonic) { clock_value += 1000; return clock_value; }
    if (number == sys_sleep_until) {
        assert(first >= static_cast<u64>(clock_value));
        assert(!requests.empty() && first <= requests.back().deadline);
        clock_value = static_cast<i64>(first);
        ++sleeps;
        return 0;
    }
    if (number == sys_ipc_name && first == static_cast<u64>(ipc_name_action::connect)) {
        assert(!send_open && !receive_open);
        assert(std::strcmp(reinterpret_cast<const char*>(second), service_name) == 0);
        *reinterpret_cast<ipc_channel*>(third) = {11, 12};
        send_open = receive_open = true;
        return 0;
    }
    if (number == sys_ipc_endpoint) {
        if (first == static_cast<u64>(ipc_endpoint_action::query_peer)) {
            assert((second == 11 && send_open) || (second == 12 && receive_open));
            *reinterpret_cast<u64*>(third) = 42;
            return 0;
        }
        if (first == static_cast<u64>(ipc_endpoint_action::close)) {
            assert((second == 11 && send_open) || (second == 12 && receive_open));
            if (second == 11) send_open = false; else receive_open = false;
            ++endpoint_closes;
            pending = false;
            return 0;
        }
    }
    if (number == 4) {
        assert(first == 11 && send_open && !pending && next_step < script.size());
        assert(third >= header_bytes && third <= sizeof(message));
        message request{};
        std::memcpy(&request, reinterpret_cast<const void*>(second), static_cast<size_t>(third));
        assert(third == header_bytes + request.length && request.version == version);
        assert(request.action == script[next_step].action);
        assert(request.sequence == requests.size() + 1 && request.deadline > static_cast<u64>(clock_value));
        requests.push_back(request);
        ++next_step;
        pending = true;
        return 0;
    }
    if (number == 5) {
        assert(first == 12 && receive_open && pending && third == sizeof(message));
        const auto& instruction = script[next_step - 1];
        if (instruction.lost_reply) return -3;
        const auto& request = requests.back();
        auto& reply = *reinterpret_cast<message*>(second);
        reply = {};
        reply.version = version;
        reply.action = request.action;
        reply.sequence = request.sequence;
        reply.object = request.action == operation::open
            ? (instruction.result == 0 ? instruction.opened_handle : 0) : request.object;
        reply.result = instruction.result;
        reply.flags = instruction.flags;
        assert(instruction.payload.size() <= payload_bytes);
        reply.length = static_cast<u32>(instruction.payload.size());
        if (reply.length) std::memcpy(reply.data, instruction.payload.data(), reply.length);
        if (instruction.corrupt == corruption::sequence) ++reply.sequence;
        if (instruction.corrupt == corruption::object) ++reply.object;
        if (instruction.late_reply) clock_value = static_cast<i64>(request.deadline);
        pending = false;
        return header_bytes + reply.length;
    }
    assert(false);
    return -1;
}
}

int main() {
    datagram_cases();
    connection_progress_cases();
    retry_and_timeout_cases();
    receive_and_datagram_rejection_cases();
    malformed_envelope_cases();
    strict_reply_shapes();
    std::printf("PASS N3 native client: groups=%u UDP-zero,required-retry,connecting,short-write,would-block,timeout-no-replay,EOF,malformed,cleanup strict-replies=1\n",
                groups);
}
