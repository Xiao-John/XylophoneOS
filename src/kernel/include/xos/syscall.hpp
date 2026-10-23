#pragma once
#include <xos/types.hpp>
#include <xos/process_abi.hpp>

namespace xos {
inline constexpr u64 sys_write = 1;
inline constexpr u64 sys_exit = 2;
inline constexpr u64 sys_yield = 3;
inline constexpr u64 sys_send = 4;
inline constexpr u64 sys_recv = 5;
inline constexpr u64 sys_getpid = 6;
inline constexpr u64 sys_ticks = 7;
inline constexpr u64 sys_read = 8;
inline constexpr u64 sys_tasklist = 9;
inline constexpr u64 sys_kill = 10;

inline constexpr i64 sys_error_invalid_handle = -1;
inline constexpr i64 sys_error_invalid_argument = -2;
inline constexpr i64 sys_error_empty = -3;
inline constexpr i64 sys_error_full = -4;
}
