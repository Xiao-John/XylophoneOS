// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
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
inline constexpr u64 sys_file_session = 27;
inline constexpr u64 sys_process_grant = 28, sys_heap_break = 29;
inline constexpr u64 sys_pipe_create = 30, sys_pipe_read = 31;
inline constexpr u64 sys_pipe_write = 32, sys_pipe_close = 33;
inline constexpr u64 sys_process_stdio = 34;
inline constexpr u64 sys_process_tls = 35;
inline constexpr u64 sys_debug_trace = 36;
inline constexpr u64 sys_process_delegate = 37;
inline constexpr u64 sys_boot_payload = 53;
inline constexpr u64 sys_process_guard = 54;
enum class process_guard_action : u64 { query = 0, begin = 1, end = 2, rearm = 3 };
struct process_guard_info { u64 owner_pid; u64 worker_pid; };
inline constexpr i64 process_error_busy = -11;
inline constexpr i64 block_error_no_device = -1, block_error_invalid = -2;
inline constexpr i64 block_error_io = -3, block_error_timeout = -4;
inline constexpr i64 block_error_denied = -5;
inline constexpr i64 process_error_invalid = -2, process_error_denied = -1;
inline constexpr i64 process_error_resources = -5, process_error_state = -6;
inline constexpr i64 process_error_would_block = -3;
inline constexpr i64 process_error_delegation = -10;
inline constexpr i64 pipe_error_broken = -7;
inline constexpr u64 process_user_begin = 0x40000000, process_user_end = 0x80000000;
inline constexpr u64 process_stack_top = process_user_end;
inline constexpr u32 process_stack_pages = 32, process_startup_pages = 4;
inline constexpr u32 process_reserved_pages = process_stack_pages + process_startup_pages;
inline constexpr u64 process_startup_begin = process_stack_top - process_startup_pages * 4096ull;
inline constexpr u64 process_stack_bottom = process_startup_begin - process_stack_pages * 4096ull;
inline constexpr u64 process_stack_guard = process_stack_bottom - 4096;
inline constexpr u64 process_image_end = process_stack_guard;
inline constexpr u64 process_heap_begin = 0x60000000, process_heap_end = 0x70000000;
// Private static-TLS allocation arena, distinct from ELF LOADs and the heap.
inline constexpr u64 process_tls_begin = 0x5fe00000, process_tls_end = process_heap_begin;
inline constexpr u64 process_tls_max_bytes = 0x100000, process_tls_max_alignment = 65536;
inline constexpr u32 process_max_pages = 65536, process_max_args = 64;
inline constexpr u32 process_max_arg_bytes = 256;
inline constexpr u32 process_max_spawn_depth = 3;
inline constexpr u32 process_max_pipe_refs = 16, process_max_pipes = 8;
inline constexpr u32 process_pipe_bytes = 4096;
inline constexpr u32 process_pipe_token_min = 65536;
inline constexpr u64 process_stdio_close = ~u64{0};
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
struct file_session_info { u64 pid; u32 request_handle; u32 response_handle; };
struct pipe_handles { u32 read_token; u32 write_token; };
static_assert(sizeof(process_page) == 24 && sizeof(process_entry) == 24);
static_assert(sizeof(startup_info) == 48 && sizeof(process_status) == 48);
static_assert(sizeof(file_session_info) == 16);
static_assert(sizeof(pipe_handles) == 8);
}
