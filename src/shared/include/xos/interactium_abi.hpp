// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <xos/abi_types.hpp>

// Interactium is a userspace protocol. It deliberately allocates no syscall
// number: the transport is supplied by the endpoint/IPC work that follows.
namespace xos::interactium {

inline constexpr u32 protocol_version = 1;
inline constexpr u32 max_windows_per_session = 8;
inline constexpr u32 max_dirty_rects = 16;

enum class message_type : u32 {
    hello = 1,
    hello_reply = 2,
    create_window = 3,
    destroy_window = 4,
    configure = 5,
    begin_frame = 6,
    write_tile = 7,
    commit_frame = 8,
    cancel_frame = 9,
    input = 10,
    focus = 11,
    close_request = 12,
    disconnect = 13,
    ack = 14,
};

enum class window_role : u32 { normal = 0, overlay = 1 };
enum class pixel_format : u32 { argb8888_premultiplied = 1 };
enum class input_kind : u32 { key_press = 1, key_release = 2, pointer = 3, resync = 4 };

enum wire_flags : u32 {
    flag_none = 0,
    flag_visible = 1u << 0,
    flag_active = 1u << 1,
    flag_opaque = 1u << 2,
};

// Every message starts with this fixed-width, little-endian header. Payloads
// are copied by the transport; no message contains a client virtual address.
struct wire_header {
    u32 version;
    u32 size;
    message_type type;
    u32 flags;
    u64 sequence;
    u64 session;
    u64 object;
    u32 payload_length;
    u32 reserved;
};

struct hello_payload {
    u32 client_version;
    u32 capabilities;
    u32 requested_width;
    u32 requested_height;
};

struct hello_reply_payload {
    u32 server_version;
    u32 capabilities;
    u32 screen_width;
    u32 screen_height;
    u64 session_epoch;
    u64 reserved;
};

struct create_window_payload {
    i32 x;
    i32 y;
    u32 width;
    u32 height;
    window_role role;
    u32 title_length;
    u32 reserved;
};

struct configure_payload {
    u64 configure_serial;
    i32 x;
    i32 y;
    u32 width;
    u32 height;
    u32 flags;
    u32 reserved;
};

struct frame_payload {
    u64 frame_serial;
    u32 width;
    u32 height;
    u32 stride;
    pixel_format format;
    u64 bytes;
};

struct tile_payload {
    u64 frame_serial;
    u32 x;
    u32 y;
    u32 width;
    u32 height;
    u32 source_offset;
    u32 source_length;
    u32 reserved;
};

struct commit_payload {
    u64 frame_serial;
    u32 dirty_rect_count;
    u32 flags;
};

struct dirty_rect { u32 x, y, width, height; };

struct input_payload {
    u64 input_sequence;
    input_kind kind;
    u32 code;
    u32 modifiers;
    u32 buttons;
    i32 x;
    i32 y;
    i32 dx;
    i32 dy;
    u32 lost;
};

struct close_payload { u32 reason; u32 reserved; };
struct status_payload { i64 result; };

static_assert(sizeof(wire_header) == 48);
static_assert(sizeof(hello_payload) == 16 && sizeof(hello_reply_payload) == 32);
static_assert(sizeof(create_window_payload) == 28 && sizeof(configure_payload) == 32);
static_assert(sizeof(frame_payload) == 32 && sizeof(tile_payload) == 40);
static_assert(sizeof(commit_payload) == 16 && sizeof(dirty_rect) == 16);
static_assert(sizeof(input_payload) == 48 && sizeof(close_payload) == 8);
static_assert(sizeof(status_payload) == 8);

} // namespace xos::interactium
