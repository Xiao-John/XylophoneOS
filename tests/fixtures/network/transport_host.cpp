// SPDX-License-Identifier: Apache-2.0
#include "transport.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace {
using namespace xos;
i64 clock_value = 1'000'000'000;
net2::message input;
std::vector<std::string> responses;
std::vector<std::string> sent_requests;
size_t offset = 0, current = 0;
u64 next_handle = 0;
bool opened = false;
unsigned cancel_count = 0, read_chunk = 7;
void scenario(std::vector<std::string> values) {
    responses = std::move(values); sent_requests.clear(); offset = current = 0;
    next_handle = 0; opened = false; cancel_count = 0; clock_value = 1'000'000'000;
}
std::string response(const std::string& body, unsigned status = 200, const std::string& fields = "") {
    return "HTTP/1.1 " + std::to_string(status) + " Test\r\nContent-Length: " + std::to_string(body.size()) +
        "\r\n" + fields + "\r\n" + body;
}
}
namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    using namespace net2;
    if (number == sys_clock_monotonic) { clock_value += 1000; return clock_value; }
    if (number == sys_sleep_until) { clock_value = static_cast<i64>(first); return 0; }
    if (number == sys_ipc_name && first == static_cast<u64>(ipc_name_action::connect)) {
        *reinterpret_cast<ipc_channel*>(third) = {11,12}; return 0;
    }
    if (number == sys_ipc_endpoint) {
        if (first == static_cast<u64>(ipc_endpoint_action::query_peer)) { *reinterpret_cast<u64*>(third) = 42; return 0; }
        if (first == static_cast<u64>(ipc_endpoint_action::close)) return 0;
    }
    if (number == 4) {
        assert(third <= sizeof(input)); std::memcpy(&input, reinterpret_cast<void*>(second), static_cast<size_t>(third)); return 0;
    }
    if (number == 5) {
        auto& output = *reinterpret_cast<message*>(second); output = {};
        output.version = version; output.sequence = input.sequence; output.action = input.action; output.object = input.object;
        switch (input.action) {
        case operation::open:
            assert(!opened && next_handle < responses.size());
            current = static_cast<size_t>(next_handle++); output.object = next_handle;
            output.flags = connected; opened = true; offset = 0; sent_requests.emplace_back(); break;
        case operation::send: {
            assert(opened); const u32 size = input.length < 11 ? input.length : 11;
            sent_requests.back().append(reinterpret_cast<char*>(input.data), size); output.result = size; break; }
        case operation::receive: {
            assert(opened); const auto& wire = responses[current];
            size_t count = wire.size() - offset;
            if (count > input.flags) count = input.flags;
            if (count > read_chunk) count = read_chunk;
            output.length = static_cast<u32>(count);
            if (count) std::memcpy(output.data, wire.data() + offset, count);
            else output.flags = eof;
            offset += count; break; }
        case operation::close: opened = false; break;
        case operation::cancel: opened = false; ++cancel_count; break;
        default: assert(false);
        }
        return header_bytes + output.length;
    }
    assert(false); return -1;
}
}

int main() {
    using namespace xos;
    unsigned char buffer[512]; browser_http::url input_url{}, final_url{}; browser_http::response parsed{};
    assert(browser_http::parse_url("http://10.0.2.2:9000/a", 22, input_url) == browser_http::error::ok);
    auto fetch = [&](unsigned max_redirects = 5) {
        net2::client client; assert(!client.connect(42));
        return browser_http::fetch(client, input_url, buffer, sizeof(buffer), u64(clock_value) + 2'000'000'000,
                                   parsed, final_url, max_redirects);
    };
    read_chunk = 1; // Header delimiter may span any of four distinct reads.
    scenario({response(std::string("ab\0cd",5),201)});
    assert(!fetch() && parsed.status == 201 && parsed.body_length == 5 &&
           !std::memcmp(buffer + parsed.body_offset,"ab\0cd",5));
    assert(sent_requests.size()==1 && sent_requests[0].find("GET /a HTTP/1.1\r\n") == 0 &&
           sent_requests[0].find("Host: 10.0.2.2:9000\r\n") != std::string::npos);
    read_chunk = 7;
    scenario({"HTTP/1.1 200 Test\r\nContent-Length: 8\r\n\r\nshort"});
    assert(fetch() == net2::io && cancel_count == 1);
    scenario({response("ok") + "extra"}); assert(fetch() == net2::invalid && cancel_count == 1);
    scenario({"HTTP/1.1 200 Test\r\nContent-Length: 999\r\n\r\n"}); assert(fetch() == net2::resources);
    scenario({"HTTP/1.1 200 Test\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n"}); assert(fetch() == net2::unsupported);
    scenario({response("",302,"Location: /next\r\n"),response("redirected")});
    assert(!fetch() && next_handle == 2 && !std::strcmp(final_url.target,"/next") && parsed.body_length == 10);
    scenario({response("",302,"Location: http://10.0.2.2:9001/next\r\n")});
    assert(fetch() == net2::denied && next_handle == 1);
    scenario({response("",302,"Location: http://10.0.2.3:9000/next\r\n")});
    assert(fetch() == net2::denied && next_handle == 1);
    scenario({response("",302,"Location: /next\r\n")});
    assert(!fetch(0) && parsed.status == 302 && next_handle == 1 && !std::strcmp(final_url.target,"/a"));
    scenario({response("",302,"Location: /next\r\n"),response("",302,"Location: /more\r\n")});
    assert(fetch(1) == net2::resources && next_handle == 2);
    scenario({response("ok")}); std::strcpy(input_url.host,"example.test"); assert(fetch() == net2::unsupported && !next_handle);
    u32 address = 0;
    assert(net2::parse_ipv4("10.0.2.2",address) && address == 0x0a000202);
    for (const char* bad : {"010.0.2.2","10.0.2","10.0.2.256","10.0.2.2x","10..2.2"}) assert(!net2::parse_ipv4(bad,address));
    std::puts("PASS N3 production SDK/HTTP: short writes, binary payload, EOF, truncation, trailing bytes, bounds, framing, same-origin redirects, redirect budget, numeric IPv4");
}
