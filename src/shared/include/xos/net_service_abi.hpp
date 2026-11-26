// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>

namespace xos::net2 {
inline constexpr char service_name[] = "net2";
inline constexpr u32 version = 2, header_bytes = 64, payload_bytes = 1024;
inline constexpr u32 client_sessions = 4, session_limit = 5, connection_limit = 8;
inline constexpr u32 connections_per_session = 2, tcp_receive_bytes = 8192, udp_queue_limit = 4;
inline constexpr u64 max_request_ns = 30'000'000'000ull, idle_ns = 60'000'000'000ull;
inline constexpr u64 reply_timeout_ns = 500'000'000ull;
inline constexpr u32 permitted_address = 0x0a000202;
enum class protocol : u16 { none = 0, tcp = 1, udp = 2 };
enum class operation : u32 {
    information = 1, open = 2, status = 3, send = 4, receive = 5,
    close = 6, cancel = 7, revoke_peer = 8, stop = 9,
    configuration = 10, configure = 11, resolve_start = 12, resolve_result = 13, resolve_cancel = 14
};
inline constexpr i64 invalid = -201, denied = -202, resources = -203, would_block = -204;
inline constexpr i64 timeout = -205, closed = -206, io = -207, unsupported = -208;
inline constexpr i64 buffer_too_small = -209, reset = -210;
inline constexpr i64 name_not_found = -211, name_no_data = -212, dns_failure = -213;
inline constexpr i64 dns_refused = -214, dns_truncated = -215, config_changed = -216, dns_expired = -217;
inline constexpr u32 configuration_revision = 1, resolve_in_a = 1, dns_name_limit = 253;
enum class network_mode : u32 { disabled = 0, static_direct = 1 };
inline constexpr u32 connecting = 1, connected = 2, eof = 4, failed = 8;
struct message {
    u32 version;
    operation action;
    u64 sequence, object, deadline;
    i64 result;
    u32 address;
    u16 port;
    protocol transport;
    u32 length, flags;
    u64 reserved;
    u8 data[payload_bytes];
};
struct information {
    u32 sessions, connections, max_sessions, max_connections;
    u32 max_payload, max_per_session, udp_dropped, reserved;
};
struct config_snapshot {
    u32 revision;
    network_mode mode;
    u64 epoch;
    u32 capabilities, address, mask, gateway, resolver, tickets;
    u64 reserved;
};
struct config_request { u32 revision; network_mode mode; u64 expected_epoch; };
struct resolve_reply { u64 epoch, expiry; u32 address, reserved; };
static_assert(__builtin_offsetof(message, data) == header_bytes);
static_assert(sizeof(message) == header_bytes + payload_bytes && sizeof(information) == 32);
static_assert(sizeof(config_snapshot) == 48 && __builtin_offsetof(config_snapshot, epoch) == 8 &&
              __builtin_offsetof(config_snapshot, reserved) == 40);
static_assert(sizeof(config_request) == 16 && __builtin_offsetof(config_request, expected_epoch) == 8);
static_assert(sizeof(resolve_reply) == 24 && __builtin_offsetof(resolve_reply, address) == 16);
}
