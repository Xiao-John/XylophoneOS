// SPDX-License-Identifier: Apache-2.0
#include "page.hpp"
#include "transport.hpp"
#include <xos/fault_sha256.hpp>
#include <xos/net_service_client.hpp>
#include <cstdio>
#include <cstring>

namespace {
using namespace xos;
using namespace xos::clarke;
char document[document_limit];
u8 rgba[frame_bytes];
}
int main(int argc, char** argv)
{
    u64 controller = 0;
    if (argc != 2 || !parse_pid(argv[1], controller)) return 2;
    bootstrap config{}; ipc_channel channel{};
    if (!child_bootstrap(controller, role::renderer, config, channel)) return 3;
    struct cleanup { ipc_channel& value; ~cleanup() { close_pair(value); } } closing{channel};
    net2::session_client raw;
    const i64 attached = raw.connect(config.network);
    net2::capability_snapshot capabilities{};
    const i64 requested = attached ? attached : raw.capabilities(deadline_after(bootstrap_ns), capabilities);
    raw.close();
    std::printf("CLARKE_RENDERER_RAW_NET connect=%lld request=%lld\n", static_cast<long long>(attached), static_cast<long long>(requested));
    packet policy{}; policy.action = operation::renderer_policy; policy.result = static_cast<i32>(requested);
    if (!send_packet(channel, policy, deadline_after(bootstrap_ns)) ||
        (requested != net2::denied && requested != net2::closed)) return 4;
    packet input{};
    const u64 deadline = deadline_after(navigation_ns);
    if (!receive_packet(channel, input, deadline) || input.action != operation::document_begin ||
        !input.navigation || input.length || input.result || !input.offset || input.offset > document_limit) return 5;
    const u64 navigation = input.navigation; const u32 length = input.offset;
    u32 position = 0;
    sha256 hash;
    while (position < length) {
        if (!receive_packet(channel, input, deadline) || input.action != operation::document_chunk ||
            input.navigation != navigation || input.result || input.offset != position ||
            !input.length || input.length > length - position) return 5;
        std::memcpy(document + position, input.data, input.length); hash.update(input.data, input.length);
        position += input.length;
    }
    u8 digest[32]; hash.finish(digest);
    if (!receive_packet(channel, input, deadline) || input.action != operation::document_end ||
        input.navigation != navigation || input.result || input.offset != length || input.length != sizeof(digest) ||
        std::memcmp(input.data, digest, sizeof(digest))) return 6;
#ifdef XOS_CLARKE_TEST_FAULT_NAVIGATION
    if (config.diagnostics && navigation == XOS_CLARKE_TEST_FAULT_NAVIGATION) {
        std::printf("CLARKE_RENDERER_INJECTED_FAULT navigation=%llu\n", static_cast<unsigned long long>(navigation));
        std::fflush(stdout); __builtin_trap();
    }
#endif
    if (!clarke_page::render(document, length, rgba)) return 7;
    if (config.diagnostics) {
        // Observe a real completed WebCore paint before its bounded IPC
        // transfer. The guest may cancel or replace this live renderer; no
        // test delay or synthetic frame participates in that path.
        std::printf("CLARKE_RENDERER_PAINTED navigation=%llu\n", static_cast<unsigned long long>(navigation));
        std::fflush(stdout);
    }
    packet output{}; output.action = operation::frame_begin; output.navigation = navigation;
    const frame_info info{viewport_width, viewport_height, viewport_width * 4, frame_bytes};
    output.length = sizeof(info); std::memcpy(output.data, &info, sizeof(info));
    if (!send_packet(channel, output, deadline)) return 8;
    sha256 frame_hash;
    for (u32 offset = 0; offset < frame_bytes;) {
        output = {}; output.action = operation::frame_chunk; output.navigation = navigation; output.offset = offset;
        output.length = frame_bytes - offset < payload_bytes ? frame_bytes - offset : payload_bytes;
        std::memcpy(output.data, rgba + offset, output.length); frame_hash.update(output.data, output.length);
        if (!send_packet(channel, output, deadline)) return 8;
        offset += output.length;
    }
    output = {}; output.action = operation::frame_end; output.navigation = navigation;
    output.offset = frame_bytes; output.length = 32; frame_hash.finish(output.data);
    if (!send_packet(channel, output, deadline)) return 8;
    if (!receive_packet(channel, input, deadline) || input.action != operation::frame_accepted ||
        input.navigation != navigation || input.result || input.offset || input.length != 32 ||
        std::memcmp(input.data, output.data, 32)) return 9;
    std::printf("CLARKE_RENDERER_FRAME navigation=%llu bytes=%u viewport=320x180\n",
                static_cast<unsigned long long>(navigation), frame_bytes);
    return 0;
}
