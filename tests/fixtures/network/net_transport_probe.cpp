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
void result(const char* label, const u8* data) {
    constexpr char digits[] = "0123456789abcdef";
    char text[128]{}; u32 count = 0;
    for (; *label; ++label) text[count++] = *label;
    for (u32 i = 0; i < 32; ++i) { text[count++] = digits[data[i] >> 4]; text[count++] = digits[data[i] & 15]; }
    constexpr char suffix[] = "\nNET2_GUEST_PASS\n";
    for (u32 i = 0; suffix[i]; ++i) text[count++] = suffix[i];
    (void)sdk::write(1, text, count);
}
int failed(i64 error) {
    sdk::print("NET2_FAIL error="); sdk::signed_decimal(error); sdk::print("\n"); return 1;
}
i64 tcp_unread_close(u64 service_pid, u16 port, const char* nonce, u64 deadline) {
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
    const i64 clock = sdk::syscall(sys_clock_monotonic);
    if (clock < 0 || sdk::syscall(sys_sleep_until, static_cast<u64>(clock) + 200'000'000ull)) return net2::io;
    for (u32 sent = 0; sent < 8192;) {
        request = {}; request.action = net2::operation::send; request.object = handle;
        request.length = 8192 - sent < net2::payload_bytes ? 8192 - sent : net2::payload_bytes;
        for (u32 i = 0; i < request.length; ++i) request.data[i] = static_cast<u8>(nonce[(sent + i) % 32]);
        status = exchange(request, reply);
        if (status <= 0) return status < 0 ? status : net2::io;
        sent += static_cast<u32>(status);
    }
    request = {}; request.action = net2::operation::close; request.object = handle;
    status = exchange(request, reply, false);
    if (status != net2::would_block) return net2::io;
    for (u32 received = 0; received < 32;) {
        request = {}; request.action = net2::operation::receive; request.object = handle; request.flags = 32 - received;
        status = exchange(request, reply); if (status) return status;
        if (!reply.length || reply.length > 32 - received) return net2::io;
        __builtin_memcpy(buffer + received, reply.data, reply.length); received += reply.length;
    }
    request = {}; request.action = net2::operation::close; request.object = handle;
    status = exchange(request, reply); if (status) return status;
    result("NET2_TCP bytes=32 data=", buffer); return 0;
}
}
extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    const auto* argv = reinterpret_cast<const char* const*>(startup->argv);
    u64 service_pid = 0, port = 0;
    if (startup->argc != 5 || (!sdk::equal(argv[1], "http") && !sdk::equal(argv[1], "udp") && !sdk::equal(argv[1], "tcp_close")) ||
        !decimal(argv[2], ~u64{0}, service_pid) || !decimal(argv[3], 65535, port) || !nonce_valid(argv[4])) return 2;
    const i64 now = sdk::syscall(sys_clock_monotonic);
    if (now < 0) return failed(net2::io);
    const u64 deadline = static_cast<u64>(now) + 15'000'000'000ull;
    if (sdk::equal(argv[1], "tcp_close")) {
        const i64 status = tcp_unread_close(service_pid, static_cast<u16>(port), argv[4], deadline);
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
        result("NET2_UDP bytes=32 data=", buffer);
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
        result("NET2_HTTP status=201 bytes=32 data=", buffer + response.body_offset);
    }
    client.close(); return 0;
}
