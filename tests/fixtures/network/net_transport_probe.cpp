// SPDX-License-Identifier: Apache-2.0
#include <xos/net_transport.hpp>
#include "transport.hpp"

namespace {
using namespace xos;
u8 buffer[65536];
bool decimal(const char* text, u64 maximum, u64& value) {
    value = 0;
    if (!text || !*text || *text == '0') return false;
    for (; *text; ++text) {
        if (*text < '0' || *text > '9') return false;
        const u64 digit = static_cast<u64>(*text - '0');
        if (value > (maximum - digit) / 10) return false;
        value = value * 10 + digit;
    }
    return value != 0;
}
bool nonce_valid(const char* value) {
    u32 count = 0;
    while (value[count]) {
        if (count >= 32 || !((value[count] >= '0' && value[count] <= '9') ||
                            (value[count] >= 'a' && value[count] <= 'f'))) return false;
        ++count;
    }
    return count == 32;
}
void result(const char* label, const char* nonce, const u8* data) {
    constexpr char digits[] = "0123456789abcdef";
    char text[192]{}; u32 count = 0;
    // A concurrent shell may already be echoing input on the current line.
    text[count++] = '\n';
    for (; *label; ++label) text[count++] = *label;
    constexpr char nonce_field[] = " nonce=";
    for (u32 i = 0; nonce_field[i]; ++i) text[count++] = nonce_field[i];
    for (u32 i = 0; i < 32; ++i) text[count++] = nonce[i];
    constexpr char data_field[] = " data=";
    for (u32 i = 0; data_field[i]; ++i) text[count++] = data_field[i];
    for (u32 i = 0; i < 32; ++i) { text[count++] = digits[data[i] >> 4]; text[count++] = digits[data[i] & 15]; }
    constexpr char suffix[] = "\nNET2_GUEST_PASS\n";
    for (u32 i = 0; suffix[i]; ++i) text[count++] = suffix[i];
    (void)sdk::write(1, text, count);
}
int failed(i64 error) {
    sdk::print("NET2_FAIL error="); sdk::signed_decimal(error); sdk::print("\n"); return 1;
}
i64 tcp_half_close(u64 service_pid, u16 port, const char* nonce, u64 deadline) {
    net2::session_client client;
    i64 status = client.connect(service_pid);
    if (status) return status;
    net2::capability_snapshot capabilities{};
    status = client.capabilities(deadline, capabilities);
    if (status || capabilities.flags != (net2::capability_readiness | net2::capability_shutdown_write))
        return status ? status : net2::unsupported;
    net2::message request{}, reply{};
    request.action = net2::operation::open; request.address = net2::permitted_address;
    request.port = port; request.transport = net2::protocol::tcp; request.deadline = deadline;
    status = client.request(request, reply);
    if (status) return status;
    const u64 handle = reply.object;
    net2::readiness_snapshot snapshot{};
    auto wait_ready = [&](u32 events) -> i64 {
        for (;;) {
            const i64 checked = client.readiness(handle, deadline, snapshot);
            if (checked) return checked;
            if (snapshot.error) return snapshot.error;
            if (snapshot.events & events) return 0;
            const i64 now = sdk::syscall(sys_clock_monotonic);
            if (now < 0 || static_cast<u64>(now) >= deadline) return net2::timeout;
            if (sdk::syscall(sys_sleep_until, static_cast<u64>(now) + 1'000'000ull)) return net2::io;
        }
    };
    status = wait_ready(net2::ready_write); if (status) return status;
    request = {}; request.action = net2::operation::send; request.object = handle;
    request.length = 32; request.deadline = deadline; __builtin_memcpy(request.data, nonce, 32);
    status = client.request(request, reply); if (status != 32) return status < 0 ? status : net2::io;
    status = client.shutdown_write(handle, deadline); if (status) return status;
    status = client.shutdown_write(handle, deadline); if (status) return status;
    // The fixture withholds its unpredictable response until it receives FIN.
    // Thus successful bytes here prove the receive path survives SHUT_WR.
    u32 received = 0;
    for (;;) {
        status = wait_ready(net2::ready_read); if (status) return status;
        if (!(snapshot.events & net2::ready_write_closed) || (snapshot.events & net2::ready_write)) return net2::io;
        request = {}; request.action = net2::operation::receive; request.object = handle;
        request.flags = 32; request.deadline = deadline;
        status = client.request(request, reply); if (status) return status;
        if (reply.length > 32 - received) return net2::io;
        __builtin_memcpy(buffer + received, reply.data, reply.length); received += reply.length;
        if (reply.flags & net2::eof) break;
    }
    if (received != 32) return net2::io;
    request = {}; request.action = net2::operation::send; request.object = handle;
    request.length = 1; request.data[0] = 1; request.deadline = deadline;
    if (client.request(request, reply) != net2::closed) return net2::io;
    request = {}; request.action = net2::operation::close; request.object = handle; request.deadline = deadline;
    status = client.request(request, reply); if (status) return status;
    result("NET2_HALF_CLOSE bytes=32", nonce, buffer);
    return 0;
}
i64 tcp_unread_close(u64 service_pid, u16 port, const char* nonce, u64 deadline,
                     bool controlled = false, bool drained = false) {
    net2::session_client client;
    i64 status = client.connect(service_pid);
    if (status) return status;
    auto exchange = [&](net2::message& input, net2::message& reply, bool retry = true) {
        input.deadline = deadline;
        for (;;) {
            const i64 result = client.request(input, reply);
            if (!retry || result != net2::would_block) return result;
            const i64 clock = sdk::syscall(sys_clock_monotonic);
            if (clock < 0 || static_cast<u64>(clock) >= deadline) return net2::timeout;
            if (sdk::syscall(sys_sleep_until, static_cast<u64>(clock) + 1'000'000ull)) return net2::io;
        }
    };
    net2::message request{}, reply{}; request.action = net2::operation::open;
    request.address = net2::permitted_address; request.port = port; request.transport = net2::protocol::tcp;
    status = exchange(request, reply); if (status) return status;
    const u64 handle = reply.object;
    while (reply.flags == net2::connecting) {
        request = {}; request.action = net2::operation::status; request.object = handle;
        status = exchange(request, reply); if (status) return status;
    }
    if (!(reply.flags & net2::connected)) return net2::io;
    request = {}; request.action = net2::operation::send; request.object = handle; request.length = 32;
    __builtin_memcpy(request.data, nonce, 32);
    status = exchange(request, reply); if (status != 32) return status < 0 ? status : net2::io;
    u32 received = 0;
    if (controlled) {
        // Receiving the first challenge byte proves that TCP processed the
        // same frame's zero-window advertisement. Leave 31 bytes unread for
        // the first close, while every queued output byte is window-blocked.
        const u32 initial = drained ? 32 : 1;
        while (received < initial) {
            request = {}; request.action = net2::operation::receive; request.object = handle; request.flags = initial - received;
            status = exchange(request, reply); if (status) return status;
            if (!reply.length || reply.length > initial - received) return net2::io;
            __builtin_memcpy(buffer + received, reply.data, reply.length); received += reply.length;
        }
    } else {
        const i64 clock = sdk::syscall(sys_clock_monotonic);
        if (clock < 0 || sdk::syscall(sys_sleep_until, static_cast<u64>(clock) + 200'000'000ull)) return net2::io;
    }
    // The real TCP_SND_BUF is 5840 bytes. A zero-window case admits 4096
    // without requiring an ACK; the drained control retains the 8192 total.
    const u32 send_bytes = controlled && !drained ? 4096 : 8192;
    for (u32 sent = 0; sent < send_bytes;) {
        request = {}; request.action = net2::operation::send; request.object = handle;
        request.length = send_bytes - sent < net2::payload_bytes ? send_bytes - sent : net2::payload_bytes;
        for (u32 i = 0; i < request.length; ++i) request.data[i] = static_cast<u8>(nonce[(sent + i) % 32]);
        status = exchange(request, reply);
        if (status <= 0) return status < 0 ? status : net2::io;
        sent += static_cast<u32>(status);
    }
    if (!drained) {
        request = {}; request.action = net2::operation::close; request.object = handle;
        status = exchange(request, reply, false);
        if (status != net2::would_block) return net2::io;
    }
    while (received < 32) {
        request = {}; request.action = net2::operation::receive; request.object = handle; request.flags = 32 - received;
        status = exchange(request, reply); if (status) return status;
        if (!reply.length || reply.length > 32 - received) return net2::io;
        __builtin_memcpy(buffer + received, reply.data, reply.length); received += reply.length;
    }
    if (drained) {
        // The peer sends this byte only in a frame ACKing all 8192 bytes.
        // Consuming it establishes the already-drained positive control.
        request = {}; request.action = net2::operation::receive; request.object = handle; request.flags = 1;
        status = exchange(request, reply); if (status) return status;
        if (reply.length != 1 || reply.data[0] != 0xa5) return net2::io;
    }
    request = {}; request.action = net2::operation::close; request.object = handle;
    status = exchange(request, reply); if (status) return status;
    if (controlled) {
        // A normal UDP message on this NIC is the peer's close-completed
        // barrier. The peer keeps its TCP window zero until this arrives.
        sdk::print(drained ? "NET2_TCP_DRAINED_CLOSE accepted=8192\n" : "NET2_TCP_QUEUED_CLOSE accepted=4096 unread=0\n");
        request = {}; request.action = net2::operation::open; request.address = net2::permitted_address;
        request.port = port + 1; request.transport = net2::protocol::udp;
        status = exchange(request, reply); if (status) return status;
        const u64 barrier = reply.object;
        request = {}; request.action = net2::operation::send; request.object = barrier; request.length = 32;
        __builtin_memcpy(request.data, nonce, 32);
        status = exchange(request, reply); if (status != 32) return status < 0 ? status : net2::io;
        request = {}; request.action = net2::operation::receive; request.object = barrier; request.flags = 32;
        status = exchange(request, reply); if (status) return status;
        if (reply.length != 32) return net2::io;
        for (u32 i = 0; i < 32; ++i) if (reply.data[i] != static_cast<u8>(nonce[i])) return net2::io;
        request = {}; request.action = net2::operation::close; request.object = barrier;
        status = exchange(request, reply); if (status) return status;
    }
    result("NET2_TCP bytes=32", nonce, buffer); return 0;
}
}
extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    const auto* argv = reinterpret_cast<const char* const*>(startup->argv);
    u64 service_pid = 0, port = 0;
    if (startup->argc != 5 || (!sdk::equal(argv[1], "http") && !sdk::equal(argv[1], "udp") &&
        !sdk::equal(argv[1], "tcp_half") && !sdk::equal(argv[1], "tcp_close") && !sdk::equal(argv[1], "tcp_queued") && !sdk::equal(argv[1], "tcp_drained")) ||
        !decimal(argv[2], ~u64{0}, service_pid) || !decimal(argv[3], 65535, port) || !nonce_valid(argv[4])) return 2;
    const i64 now = sdk::syscall(sys_clock_monotonic);
    if (now < 0) return failed(net2::io);
    const u64 deadline = static_cast<u64>(now) + 15'000'000'000ull;
    if (sdk::equal(argv[1], "tcp_half")) {
        const i64 status = tcp_half_close(service_pid, static_cast<u16>(port), argv[4], deadline);
        return status ? failed(status) : 0;
    }
    if (sdk::equal(argv[1], "tcp_close") || sdk::equal(argv[1], "tcp_queued") || sdk::equal(argv[1], "tcp_drained")) {
        const bool controlled = !sdk::equal(argv[1], "tcp_close");
        if (controlled && port == 65535) return 2;
        const i64 status = tcp_unread_close(service_pid, static_cast<u16>(port), argv[4], deadline,
                                             controlled, sdk::equal(argv[1], "tcp_drained"));
        return status ? failed(status) : 0;
    }
    net2::client client;
    i64 status = client.connect(service_pid);
    if (status) return failed(status);
    if (sdk::equal(argv[1], "udp")) {
        u64 connection = 0;
        status = client.open(net2::protocol::udp, net2::permitted_address, static_cast<u16>(port), deadline, connection);
        if (status) return failed(status);
        status = client.send_datagram(connection, reinterpret_cast<const u8*>(argv[4]), 32, deadline);
        if (status != 32) return failed(status < 0 ? status : net2::io);
        u32 required = 0;
        status = client.receive_datagram(connection, buffer, sizeof(buffer), deadline, required);
        if (status != 32) return failed(status < 0 ? status : net2::io);
        status = client.close_connection(connection, deadline);
        if (status) return failed(status);
        result("NET2_UDP bytes=32", argv[4], buffer);
    } else {
        char address[96]{}; u32 size = 0;
        const char* prefix = "http://10.0.2.2:";
        for (u32 i = 0; prefix[i]; ++i) address[size++] = prefix[i];
        for (u32 i = 0; argv[3][i]; ++i) address[size++] = argv[3][i];
        address[size++] = '/';
        for (u32 i = 0; i < 32; ++i) address[size++] = argv[4][i];
        browser_http::url target{}, final_url{};
        browser_http::response response{};
        if (browser_http::parse_url(address, size, target) != browser_http::error::ok) return failed(net2::invalid);
        status = browser_http::fetch(client, target, buffer, sizeof(buffer), deadline, response, final_url, 0);
        if (status) return failed(status);
        if (response.status != 201 || response.body_length != 32) return failed(net2::io);
        result("NET2_HTTP status=201 bytes=32", argv[4], buffer + response.body_offset);
    }
    client.close(); return 0;
}
