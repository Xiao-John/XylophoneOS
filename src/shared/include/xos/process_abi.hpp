#pragma once
#include <xos/abi_types.hpp>

namespace xos {
// Internal E04 ABI; rebuild kernel and SDK together. No Linux ABI promise.
inline constexpr u64 sys_handle_write = 11, sys_handle_read = 12, sys_handle_close = 13;
inline constexpr u64 sys_image_info = 14, sys_image_read = 15;
inline constexpr u64 sys_process_create = 16, sys_process_map = 17;
inline constexpr u64 sys_process_start = 18, sys_process_abort = 19;
inline constexpr u64 sys_process_wait = 20, sys_process_stats = 21;
inline constexpr u64 sys_ipc_handles = 22;
inline constexpr u64 sys_block_read = 23, sys_block_write = 24;
inline constexpr u64 sys_block_sync = 25, sys_block_info = 26;
inline constexpr i64 block_error_no_device = -1, block_error_invalid = -2;
inline constexpr i64 block_error_io = -3, block_error_timeout = -4;
inline constexpr i64 block_error_denied = -5;
inline constexpr i64 process_error_invalid = -2, process_error_denied = -1;
inline constexpr i64 process_error_resources = -5, process_error_state = -6;
inline constexpr i64 process_error_would_block = -3;
inline constexpr u64 process_user_begin = 0x40000000, process_user_end = 0x80000000;
inline constexpr u64 process_stack_top = process_user_end;
inline constexpr u64 process_stack_bottom = process_stack_top - 4 * 4096;
inline constexpr u64 process_image_end = process_stack_bottom - 4096;
inline constexpr u32 process_max_pages = 64, process_max_args = 8;
inline constexpr u64 startup_magic = 0x3154524154535358;
inline constexpr u32 map_read = 4, map_write = 2, map_execute = 1;

struct image_info { u64 size; char name[16]; };
struct image_read_request { u64 offset; u64 destination; u64 length; };
struct process_page { u64 address; u64 source; u32 length; u32 permissions; };
struct process_entry { u64 entry; u64 stack; u64 startup; };
struct startup_info {
    u64 magic;
    u32 version;
    u32 size;
    u32 argc;
    u32 handle_count;
    u64 argv;
    u32 handles[3];
    u32 reserved;
};
enum class process_outcome : u32 { exited = 1, faulted = 2, killed = 3 };
struct process_status {
    u32 version;
    process_outcome outcome;
    u64 pid;
    i64 code;
    u64 vector;
    u64 address;
    u64 instruction;
};
struct process_stats { u32 free_pages; u32 tasks; u32 completions; u32 reserved; };
static_assert(sizeof(process_page) == 24 && sizeof(process_entry) == 24);
static_assert(sizeof(startup_info) == 48 && sizeof(process_status) == 48);
}
