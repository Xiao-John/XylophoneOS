// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>

namespace xos::terminal {
// User-space service protocol, not a kernel syscall or POSIX termios ABI.
inline constexpr u32 version = 2, data_bytes = 256;
enum class operation : u32 { read = 1, write = 2, statistics = 3, stop = 4, read_until = 5, cancel = 6 };
inline constexpr i64 interrupted = -19;
// read_until uses an absolute monotonic ns deadline; UINT64_MAX means infinite.
struct request { u32 version, size, operation, length; u64 sequence, deadline_ns; u8 data[data_bytes]; };
struct response {
    u32 version, size, length, reserved;
    u64 sequence;
    i64 result;
    u64 software_drops, hardware_overruns, parity_errors, framing_errors, breaks;
    u8 data[data_bytes];
};
static_assert(sizeof(request) == 288 && sizeof(response) == 328);
}
