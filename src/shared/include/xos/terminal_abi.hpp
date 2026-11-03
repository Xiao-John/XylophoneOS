// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>

namespace xos::terminal {
// User-space service protocol, not a kernel syscall or POSIX termios ABI.
inline constexpr u32 version = 2, data_bytes = 256;
enum class operation : u32 { read = 1, write = 2, statistics = 3, stop = 4, read_until = 5, cancel = 6, write_until = 7, attach = 8, detach = 9, mode_get = 10, mode_set = 11, read_mode = 12, drain = 13, flush_input = 14, wait_readable = 15, fork_attach = 16 };
enum class mode_action : u32 { now = 0, drain = 1, drain_flush_input = 2 };
inline constexpr i64 interrupted = -19;
// Initial noncanonical, no-echo 115200 8N1 profile. Nonzero flags are not
// implemented. vmin/vtime support (1,0), (0,0), and (0,1..255).
struct mode { u32 iflag, oflag, cflag, lflag, ispeed, ospeed, vmin, vtime; };
inline constexpr mode default_mode{0, 0, 0, 0, 115200, 115200, 1, 0};
inline constexpr bool valid_mode(const mode& value) {
    return value.iflag == 0 && value.oflag == 0 && value.cflag == 0 && value.lflag == 0 &&
           value.ispeed == 115200 && value.ospeed == 115200 &&
           ((value.vmin == 1 && value.vtime == 0) || (value.vmin == 0 && value.vtime <= 255));
}
static_assert(sizeof(mode) == 32);
struct session_channels { u32 incoming, outgoing; u64 peer_pid; };
static_assert(sizeof(session_channels) == 16);
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
