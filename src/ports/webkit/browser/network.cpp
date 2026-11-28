// SPDX-License-Identifier: Apache-2.0
#include "https.hpp"
#include "transport.hpp"
#include <xos/fault_sha256.hpp>
#include <cstdio>
#include <cstring>

namespace {
using namespace xos;
using namespace xos::clarke;
u8 document[browser_http::max_headers + document_limit];
}
int main(int argc, char** argv)
{
    u64 controller = 0;
    if (argc != 2 || !parse_pid(argv[1], controller)) return 2;
    bootstrap config{}; ipc_channel channel{};
    if (!child_bootstrap(controller, role::network, config, channel)) return 3;
    struct cleanup { ipc_channel& value; ~cleanup() { close_pair(value); } } closing{channel};
    packet input{};
    if (!receive_packet(channel, input, deadline_after(bootstrap_ns)) || input.action != operation::fetch ||
        !input.navigation || input.offset || input.result || !valid_url(input.data, input.length)) return 4;
    const u64 navigation = input.navigation;
    browser_http::url target{};
    i64 result = browser_http::parse_url(reinterpret_cast<const char*>(input.data), input.length, target) ==
        browser_http::error::ok ? 0 : net2::invalid;
    browser_http::response response{};
    const u64 deadline = deadline_after(bootstrap_ns);
    if (!result && target.protocol == browser_http::scheme::http) {
        net2::client client; browser_http::url final_url{};
        result = client.connect(config.network);
        if (!result) result = browser_http::fetch(client, target, document, sizeof(document), deadline, response, final_url, 0);
        client.close();
    } else if (!result) result = clarke_https::fetch(config.network, target, document, sizeof(document), deadline, response);
    if (!result && (response.status != 200 || !response.body_length || response.body_length > document_limit)) result = net2::invalid;
    packet output{}; output.navigation = navigation;
    if (result) {
        output.action = operation::status; output.result = static_cast<i32>(result);
        (void)send_packet(channel, output, deadline_after(bootstrap_ns));
        std::printf("CLARKE_NETWORK_FAILED navigation=%llu result=%lld\n",
                    static_cast<unsigned long long>(navigation), static_cast<long long>(result));
        return 5;
    }
    output.action = operation::document_begin; output.offset = static_cast<u32>(response.body_length);
    const u64 transfer_deadline = deadline_after(bootstrap_ns);
    if (!send_packet(channel, output, transfer_deadline)) return 6;
    sha256 hash;
    for (u32 offset = 0; offset < response.body_length;) {
        output = {}; output.action = operation::document_chunk; output.navigation = navigation; output.offset = offset;
        const u32 left = static_cast<u32>(response.body_length) - offset;
        output.length = left < payload_bytes ? left : payload_bytes;
        std::memcpy(output.data, document + response.body_offset + offset, output.length); hash.update(output.data, output.length);
        if (!send_packet(channel, output, transfer_deadline)) return 6;
        offset += output.length;
    }
    output = {}; output.action = operation::document_end; output.navigation = navigation;
    output.offset = static_cast<u32>(response.body_length); output.length = 32; hash.finish(output.data);
    if (!send_packet(channel, output, transfer_deadline)) return 6;
    // Keep the ordinary broker alive as the positive control while the denied
    // renderer tries raw net2. Only this authenticated controller can request it.
    for (;;) {
        if (!receive_packet(channel, input, deadline_after(navigation_ns))) return 7;
        if (input.action == operation::close && input.navigation == navigation && !input.length && !input.result && !input.offset) return 0;
        if (!config.diagnostics || input.action != operation::network_probe || input.navigation != navigation ||
            input.length != sizeof(u64) || input.result || input.offset) return 8;
        u64 renderer = 0; std::memcpy(&renderer, input.data, sizeof(renderer));
        if (!renderer) return 8;
        net2::session_client ordinary; net2::capability_snapshot capabilities{}; net2::peer_policy_snapshot snapshot{};
        const i64 connected = ordinary.connect(config.network);
        const i64 alive = connected ? connected : ordinary.capabilities(deadline_after(bootstrap_ns), capabilities);
        const i64 release = alive ? alive : ordinary.peer_policy(net2::peer_policy_action::release_retired,
            renderer, deadline_after(bootstrap_ns), snapshot);
        ordinary.close();
        output = {}; output.action = operation::network_probe; output.navigation = navigation;
        output.result = static_cast<i32>(release); output.offset = alive ? 0 : 1;
        if (!send_packet(channel, output, deadline_after(bootstrap_ns))) return 9;
        std::printf("CLARKE_BROKER_POLICY navigation=%llu live=%lld release=%lld\n",
                    static_cast<unsigned long long>(navigation), static_cast<long long>(alive), static_cast<long long>(release));
    }
}
