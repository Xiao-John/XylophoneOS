// SPDX-License-Identifier: Apache-2.0
#include "pumpkin/native_ipc.cpp"
#include "pumpkin/native_ipc_client.cpp"
#include <cassert>
#include <cstdio>
#include <cstring>

using namespace xos;
using namespace xos::user::pumpkin;

namespace {
constexpr u64 ipc_send_syscall = 4;
constexpr u64 ipc_receive_syscall = 5;

struct ipc_fixture {
    i64 readiness = 0;
    i64 clock = 5;
    i64 enqueue_clock = 5;
    bool incoming = false;
    u32 reads = 0;
    u32 sent = 0;
    wire_request request;
} fixture;

transport_session transport() {
    transport_session session{};
    session.channel = {1, 2};
    session.expires = connection_lifetime_ns;
    return session;
}
}

i64 xos::sdk::syscall(u64 number, u64 first, u64 second, u64 third) {
    switch (number) {
    case sys_ipc_wait:
        assert(first == 1 && second == static_cast<u64>(ipc_wait_mode::try_send));
        return fixture.readiness;
    case sys_clock_monotonic:
        return fixture.clock;
    case ipc_receive_syscall:
        assert(first == 2 && third == sizeof(wire_request));
        ++fixture.reads;
        if (!fixture.incoming) {
            return process_error_would_block;
        }
        std::memcpy(reinterpret_cast<void*>(second), &fixture.request, sizeof(fixture.request));
        fixture.incoming = false;
        return sizeof(wire_request);
    case ipc_send_syscall: {
        assert(first == 1 && third == sizeof(wire_reply));
        wire_reply response;
        std::memcpy(&response, reinterpret_cast<const void*>(second), sizeof(response));
        assert(valid_reply(fixture.request, response));
        ++fixture.sent;
        fixture.clock = fixture.enqueue_clock;
        return 0;
    }
    default:
        assert(false);
        return -1;
    }
}

int main() {
    service_core core;
    auto session = transport();
    session.reply_expires = 10;
    u64 now = 11;
    assert(process_request(core, session, now, false) == progress::keep);
    assert(session.reply_expires == 0 && fixture.reads == 1);

    session.reply_expires = 10;
    fixture.readiness = process_error_would_block;
    assert(process_request(core, session, now, false) == progress::drop);
    assert(fixture.reads == 1);
    std::puts("PASS elapsed reply budget only drops an occupied reply slot");

    fixture = {};
    session = transport();
    fixture.request.operation = wire_operation::lookup_account;
    fixture.request.sequence = 1;
    fixture.request.deadline = max_request_ns;
    fixture.request.name_length = 1;
    fixture.request.name[0] = 'a';
    fixture.incoming = true;
    fixture.enqueue_clock = fixture.clock + static_cast<i64>(2 * reply_budget_ns);
    now = 0;
    assert(process_request(core, session, now, false) == progress::keep);
    assert(fixture.sent == 1 && now == static_cast<u64>(fixture.enqueue_clock));
    assert(session.reply_expires == now + reply_budget_ns);
    fixture.readiness = process_error_would_block;
    now += reply_budget_ns - 1;
    assert(process_request(core, session, now, false) == progress::keep);
    ++now;
    assert(process_request(core, session, now, false) == progress::drop);
    std::puts("PASS full reply-read budget starts after successful enqueue");
}
