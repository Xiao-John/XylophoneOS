// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "protocol.hpp"
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

namespace xos::clarke {
inline u64 now() {
    const i64 value = sdk::syscall(sys_clock_monotonic);
    return value < 0 ? 0 : static_cast<u64>(value);
}
inline u64 deadline_after(u64 duration) {
    const u64 value = now();
    return value && value <= ~u64{0} - duration ? value + duration : 0;
}
inline void close_pair(ipc_channel& channel) {
    if (channel.send) (void)sdk::ipc_channel_close(channel.send);
    if (channel.receive) (void)sdk::ipc_channel_close(channel.receive);
    channel = {};
}
inline bool peer_matches(const ipc_channel& channel, u64 peer) {
    u64 a = 0, b = 0;
    return peer && channel.send && channel.receive && channel.send != channel.receive &&
        !sdk::ipc_endpoint_peer(channel.send, a) && !sdk::ipc_endpoint_peer(channel.receive, b) && a == peer && b == peer;
}
inline bool send_packet(const ipc_channel& channel, const packet& value, u64 deadline) {
    if (!valid_packet(value, header_bytes + value.length)) return false;
    for (;;) {
        const u64 clock = now();
        if (!clock || clock >= deadline) return false;
        const i64 result = sdk::ipc_send(channel.send, &value, header_bytes + value.length);
        if (!result) return true;
        if (result != ipc_error_full || sdk::ipc_wait_until(channel.send, ipc_wait_mode::send, deadline)) return false;
    }
}
inline i64 receive_now(const ipc_channel& channel, packet& value) {
    value = {};
    const i64 result = sdk::ipc_recv(channel.receive, &value, sizeof(value));
    if (result < 0) return result;
    return valid_packet(value, result) ? 0 : process_error_invalid;
}
inline bool receive_packet(const ipc_channel& channel, packet& value, u64 deadline) {
    for (;;) {
        const u64 clock = now();
        if (!clock || clock >= deadline) return false;
        const i64 result = receive_now(channel, value);
        if (!result) return true;
        if (result != process_error_would_block || sdk::ipc_wait_until(channel.receive, ipc_wait_mode::receive, deadline)) return false;
    }
}
inline bool parse_pid(const char* text, u64& value) {
    value = 0;
    if (!text || !*text) return false;
    for (; *text; ++text) {
        if (*text < '0' || *text > '9' || value > (~u64{0} - (*text - '0')) / 10) return false;
        value = value * 10 + (*text - '0');
    }
    return value != 0;
}
// The trusted parent owns two short-lived sys81 bootstrap channels. Each
// runnable child creates its own private sys84 pair, avoiding the parent's
// per-owner private-pair quota. Kernel peer checks bind both exchanges.
inline bool child_bootstrap(u64 controller, role expected, bootstrap& config, ipc_channel& channel) {
    if (!controller || controller == sdk::pid()) return false;
    u32 incoming = 0, outgoing = 0;
    for (u32 index = 0; index < 16; ++index) {
        channel_info item{};
        const i64 result = sdk::channel_get(index, item);
        if (result == thread_error_not_found) break;
        if (result != 0) return false;
        if (item.version != channel_version || item.size != sizeof(item) || item.peer_pid != controller ||
            item.controller_pid != controller) continue;
        if (item.rights == channel_receive) { if (incoming) return false; incoming = item.handle; }
        else if (item.rights == channel_send) { if (outgoing) return false; outgoing = item.handle; }
    }
    if (!incoming || !outgoing) return false;
    const u64 deadline = deadline_after(bootstrap_ns);
    for (;;) {
        const u64 clock = now();
        if (!clock || clock >= deadline) return false;
        const i64 received = sdk::read(incoming, &config, sizeof(config));
        if (received == sizeof(config)) break;
        if (received != process_error_would_block || sdk::channel_wait(incoming, deadline)) return false;
    }
    if (config.magic != wire_magic || config.version != wire_version || config.size != sizeof(config) ||
        config.kind != expected || config.controller != controller || config.endpoints.send || config.endpoints.receive ||
        config.width != viewport_width || config.height != viewport_height || config.reserved || config.diagnostics > 1 ||
        (expected == role::ui ? config.network != 0 : config.network == 0)) return false;
    if (sdk::ipc_channel_create(controller, channel) || !peer_matches(channel, controller)) { close_pair(channel); return false; }
    config.endpoints = {channel.receive, channel.send};
    if (sdk::write(outgoing, &config, sizeof(config)) != sizeof(config)) { close_pair(channel); return false; }
    packet ready{}; ready.action = operation::ready;
    ready.offset = static_cast<u32>(expected);
    if (!send_packet(channel, ready, deadline)) { close_pair(channel); return false; }
    // Parent closes both sys81 channels only after consuming this response.
    return true;
}
}
