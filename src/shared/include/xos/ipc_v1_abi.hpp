// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>

namespace xos {
// IPC v1 stable ABI. Runtime support is separately gated by guest qualification
// and is advertised only by SDK profiles whose feature matrix has passed.
inline constexpr u64 sys_ipc_v1 = 88;
inline constexpr u32 ipc_v1_version = 1;
inline constexpr u32 ipc_v1_max_message_bytes = 256;
inline constexpr u32 ipc_v1_max_handles_per_process = 8;
inline constexpr u32 ipc_v1_max_endpoints_system = 32;
inline constexpr u32 ipc_v1_max_pending_calls = 32;
inline constexpr u32 ipc_v1_max_queue_per_endpoint = 8;
inline constexpr u32 ipc_v1_max_reply_tokens_per_process = 8;
inline constexpr u64 ipc_v1_deadline_poll = 0;
inline constexpr u64 ipc_v1_deadline_infinite = ~u64{0};

enum class ipc_v1_action : u64 {
    query_features = 0,
    endpoint_create = 1,
    endpoint_delegate = 2,
    endpoint_close = 3,
    call = 4,
    receive = 5,
    reply = 6,
    reply_receive = 7
};

enum class ipc_v1_right : u32 {
    call = 1u << 0,
    receive = 1u << 1,
    manage = 1u << 2,
    delegate = 1u << 3
};
inline constexpr u32 ipc_v1_right_all = 0x0fu;

enum class ipc_v1_feature : u64 {
    endpoint_call = 1ull << 0,
    deadline = 1ull << 1,
    notification = 1ull << 2,
    wait_set = 1ull << 3,
    bulk_grant = 1ull << 4
};
inline constexpr u64 ipc_v1_feature_known_mask = 0x1full;
inline constexpr u64 ipc_v1_feature_ip2_mask =
    static_cast<u64>(ipc_v1_feature::endpoint_call) |
    static_cast<u64>(ipc_v1_feature::deadline);

// These values are scoped to sys_ipc_v1 and are not errno values.
enum class ipc_v1_error : i64 {
    invalid_handle = -101,
    denied = -102,
    invalid_argument = -103,
    unsupported = -104,
    would_block = -105,
    queue_full = -106,
    resources = -107,
    closed = -108,
    timeout = -109,
    buffer_too_small = -110,
    stale_token = -111,
    state = -112,
    address = -113
};

enum class ipc_v1_call_phase : u32 {
    not_delivered = 0,
    delivered = 1,
    replied = 2
};
inline constexpr u32 ipc_v1_reply_consumed = 1u << 0;

struct ipc_v1_header {
    u32 version;
    u32 size;
    u64 reserved;
};

struct ipc_v1_feature_query {
    ipc_v1_header header;
    u64 known_features;
    u64 supported_features;
    u32 max_message_bytes;
    u32 max_handles_per_process;
    u32 max_endpoints_system;
    u32 max_pending_calls;
    u32 max_queue_per_endpoint;
    u32 max_reply_tokens_per_process;
    u64 reserved[2];
};

struct ipc_v1_endpoint_create {
    ipc_v1_header header;
    u32 rights;
    u32 flags;
    u64 handle_out;
    u64 reserved[2];
};

struct ipc_v1_endpoint_delegate {
    ipc_v1_header header;
    u64 handle;
    u64 target_pid;
    u64 badge;
    u32 rights;
    u32 flags;
    u64 handle_out;
    u64 reserved[2];
};

struct ipc_v1_endpoint_close {
    ipc_v1_header header;
    u64 handle;
    u64 reserved[2];
};

struct ipc_v1_call {
    ipc_v1_header header;
    u64 handle;
    u64 deadline_ns;
    u64 label;
    u64 send_buffer;
    u64 reply_buffer;
    u32 send_length;
    u32 reply_capacity;
    u32 reply_length_out;
    u32 phase_out;
    u64 reply_label_out;
    u64 reserved;
};

struct ipc_v1_receive {
    ipc_v1_header header;
    u64 handle;
    u64 deadline_ns;
    u64 buffer;
    u32 capacity;
    u32 message_length_out;
    u64 label_out;
    u64 badge_out;
    u64 reply_token_out;
    u64 reserved[2];
};

struct ipc_v1_reply {
    ipc_v1_header header;
    u64 reply_token;
    u64 label;
    u64 buffer;
    u32 length;
    u32 reserved32;
    u64 reserved[2];
};

struct ipc_v1_reply_receive {
    ipc_v1_header header;
    u64 reply_token;
    u64 reply_label;
    u64 reply_buffer;
    u32 reply_length;
    u32 receive_capacity;
    u64 receive_handle;
    u64 deadline_ns;
    u64 receive_buffer;
    u32 reply_consumed_out;
    u32 receive_length_out;
    u64 label_out;
    u64 badge_out;
    u64 next_reply_token_out;
    u64 reserved[2];
};

static_assert(sizeof(ipc_v1_header) == 16);
static_assert(sizeof(ipc_v1_feature_query) == 72);
static_assert(sizeof(ipc_v1_endpoint_create) == 48);
static_assert(sizeof(ipc_v1_endpoint_delegate) == 72);
static_assert(sizeof(ipc_v1_endpoint_close) == 40);
static_assert(sizeof(ipc_v1_call) == 88);
static_assert(sizeof(ipc_v1_receive) == 88);
static_assert(sizeof(ipc_v1_reply) == 64);
static_assert(sizeof(ipc_v1_reply_receive) == 120);
static_assert(__builtin_offsetof(ipc_v1_header, reserved) == 8);
static_assert(__builtin_offsetof(ipc_v1_feature_query, known_features) == 16 &&
              __builtin_offsetof(ipc_v1_feature_query, max_message_bytes) == 32 &&
              __builtin_offsetof(ipc_v1_feature_query, reserved) == 56);
static_assert(__builtin_offsetof(ipc_v1_endpoint_create, handle_out) == 24);
static_assert(__builtin_offsetof(ipc_v1_endpoint_delegate, handle_out) == 48);
static_assert(__builtin_offsetof(ipc_v1_call, send_buffer) == 40 &&
              __builtin_offsetof(ipc_v1_call, phase_out) == 68 &&
              __builtin_offsetof(ipc_v1_call, reply_label_out) == 72 &&
              __builtin_offsetof(ipc_v1_call, reserved) == 80);
static_assert(__builtin_offsetof(ipc_v1_receive, label_out) == 48 &&
              __builtin_offsetof(ipc_v1_receive, reply_token_out) == 64);
static_assert(__builtin_offsetof(ipc_v1_reply, buffer) == 32 &&
              __builtin_offsetof(ipc_v1_reply, reserved) == 48);
static_assert(__builtin_offsetof(ipc_v1_reply_receive, receive_handle) == 48 &&
              __builtin_offsetof(ipc_v1_reply_receive, reply_consumed_out) == 72 &&
              __builtin_offsetof(ipc_v1_reply_receive, reserved) == 104);
}
