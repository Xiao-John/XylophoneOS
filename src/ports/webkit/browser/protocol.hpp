// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/process_abi.hpp>

namespace xos::clarke {
inline constexpr u32 wire_magic = 0x314b4c43, wire_version = 1;
inline constexpr u32 packet_bytes = 4096, header_bytes = 32, payload_bytes = packet_bytes - header_bytes;
inline constexpr u32 viewport_width = 320, viewport_height = 180, frame_bytes = viewport_width * viewport_height * 4;
inline constexpr u32 document_limit = 65536, url_limit = 2048;
inline constexpr u64 bootstrap_ns = 3'000'000'000ull, navigation_ns = 15'000'000'000ull;
inline constexpr u64 control_quantum_ns = 20'000'000ull;
enum class role : u32 { ui = 1, network = 2, renderer = 3 };
enum class operation : u32 {
    ready = 1, navigate = 2, cancel = 3, close = 4, fetch = 5,
    document_begin = 6, document_chunk = 7, document_end = 8,
    frame_begin = 9, frame_chunk = 10, frame_end = 11, presented = 12,
    status = 13, network_probe = 14, renderer_policy = 15, frame_accepted = 16
};
enum class outcome : i32 { ok = 0, cancelled = -1, protocol = -2, policy = -3,
    network = -4, renderer = -5, deadline = -6, resources = -7 };
struct packet {
    u32 magic = wire_magic, version = wire_version;
    operation action{};
    u32 length = 0;
    u64 navigation = 0;
    i32 result = 0;
    u32 offset = 0;
    u8 data[payload_bytes]{};
};
struct bootstrap {
    u32 magic = wire_magic, version = wire_version, size = sizeof(bootstrap);
    role kind{};
    u64 controller = 0, network = 0;
    ipc_channel endpoints{};
    u32 width = viewport_width, height = viewport_height, diagnostics = 0, reserved = 0;
};
struct frame_info { u32 width, height, stride, bytes; };
static_assert(sizeof(packet) == packet_bytes && __builtin_offsetof(packet, data) == header_bytes);
static_assert(sizeof(bootstrap) == 56 && sizeof(frame_info) == 16);
inline bool valid_packet(const packet& value, i64 received) {
    return received >= header_bytes && value.magic == wire_magic && value.version == wire_version &&
        value.action >= operation::ready && value.action <= operation::frame_accepted &&
        value.length <= payload_bytes && static_cast<u64>(received) == header_bytes + value.length;
}
inline bool valid_url(const u8* value, u32 length) {
    if (!length || length > url_limit) return false;
    for (u32 i = 0; i < length; ++i) if (value[i] < 0x21 || value[i] > 0x7e) return false;
    return true;
}
inline bool valid_intent(const packet& value, u64 last_navigation, u64 current_navigation) {
    if (value.result || value.offset) return false;
    switch (value.action) {
    case operation::navigate: return value.navigation > last_navigation && valid_url(value.data, value.length);
    case operation::cancel: return value.navigation == current_navigation && !value.length;
    case operation::close: return !value.navigation && !value.length;
    case operation::presented: return value.navigation == current_navigation && value.length == 32;
    default: return false;
    }
}
}
