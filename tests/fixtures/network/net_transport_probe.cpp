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
    char text[65]{};
    for (u32 i = 0; i < 32; ++i) { text[i * 2] = digits[data[i] >> 4]; text[i * 2 + 1] = digits[data[i] & 15]; }
    sdk::print(label); sdk::print(text); sdk::print("\nNET2_GUEST_PASS\n");
}
int failed(i64 error) {
    sdk::print("NET2_FAIL error="); sdk::signed_decimal(error); sdk::print("\n"); return 1;
}
}
extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    const auto* argv = reinterpret_cast<const char* const*>(startup->argv);
    u64 service_pid = 0, port = 0;
    if (startup->argc != 5 || (!sdk::equal(argv[1], "http") && !sdk::equal(argv[1], "udp")) ||
        !decimal(argv[2], ~u64{0}, service_pid) || !decimal(argv[3], 65535, port) || !nonce_valid(argv[4])) return 2;
    const i64 now = sdk::syscall(sys_clock_monotonic);
    if (now < 0) return failed(net2::io);
    const u64 deadline = static_cast<u64>(now) + 15'000'000'000ull;
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
