// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>
namespace xos::net {
inline constexpr char service_name[] = "net";
inline constexpr u32 version = 1, frame_bytes = 1514, header_bytes = 32;
enum class operation : u32 { information = 1, transmit = 2, receive = 3, stop = 4 };
struct message { u32 version; operation action; u64 sequence; i64 result; u32 length, reserved; u8 data[frame_bytes]; };
struct bootstrap { u32 version, size; u64 grant; };
static_assert(__builtin_offsetof(message, data) == header_bytes && sizeof(bootstrap) == 16);
}
