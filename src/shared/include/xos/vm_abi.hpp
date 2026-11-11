// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>

namespace xos {
inline constexpr u64 sys_vm = 67;
inline constexpr u32 vm_abi_version = 1;
inline constexpr u64 vm_page_size = 4096;
inline constexpr u64 vm_arena_begin = 0x100000000000ull;
inline constexpr u64 vm_arena_end = 0x200000000000ull;
enum class vm_operation : u32 { info = 0, reserve = 1, commit = 2, protect = 3, decommit = 4, unmap = 5 };
enum class vm_protection : u32 { none = 0, read = 1, read_write = 3, read_execute = 5 };
inline constexpr u32 vm_exact_nonreplace = 1;
inline constexpr i64 vm_error_invalid = -1, vm_error_address = -2, vm_error_denied = -3;
inline constexpr i64 vm_error_resources = -4, vm_error_busy = -5, vm_error_unmapped = -6;
inline constexpr i64 vm_error_collision = -7, vm_error_closing = -8;
struct vm_request {
    u32 version, size, operation, flags;
    u64 address, length, alignment;
    u32 protection, reserved0;
    u64 reserved1, reserved2;
};
static_assert(sizeof(vm_request) == 64);
}
