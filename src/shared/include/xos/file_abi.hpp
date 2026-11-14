// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#pragma once
#include <xos/abi_types.hpp>

namespace xos::file {
// Internal E08 file-service ABI. Rebuild the kernel, service and SDK together.
inline constexpr u32 request_magic = 0x51455246;  // FREQ
inline constexpr u32 response_magic = 0x53455246; // FRES
// Operations appended after E08 keep the v2 wire layout so existing static
// tools remain usable. New operations are feature-detected by their result.
inline constexpr u16 abi_version = 2;
inline constexpr u32 message_size = 4096;
inline constexpr u32 max_name = 256; // UTF-8 bytes including room for NUL.
inline constexpr u32 fat32_max_file_bytes = 0xfffffffeu;
inline constexpr u32 max_block_bench_bytes = 8 * 1024 * 1024;
inline constexpr u32 max_open = 16;
inline constexpr u32 max_sessions = 8;
inline constexpr u32 max_open_descriptions = 32;
inline constexpr u32 request_data_size = message_size - 40 - max_name;
inline constexpr u32 response_data_size = message_size - 42 - max_name;

enum class op : u16 {
    ping = 1, list = 2, stat = 3, open = 4, read = 5, write = 6, seek = 7,
    close = 8, replace_begin = 9, replace_chunk = 10, replace_commit = 11,
    replace_abort = 12, remove = 13, sync = 14, mkdir = 15, rename = 16,
    block_bench = 17, fstat = 18,
    transfer = 19,
    maintenance_acquire = 23, maintenance_release = 24,
    truncate = 25, // handle + offset=size; FatFs-backed, regular writable file only.
    cwd_set = 26, // path, or an owned directory handle; survives same-PID exec.
    cwd_get = 27, // canonical absolute name; unlinked cwd reports not_found.
    resolve_path = 28, // resolve against the session cwd, return absolute name.
    anonymous_seal = 22, // irrevocably remove write access from an anonymous instance
    anonymous = 21, // private disk-backed open description, unlinked at last close
    clone_session = 20, // source authenticated by session; offset = fork child PID
    set_metadata = 29, // FAT honest subset: RDO + mtime; payload in request.data.
};

enum seek_origin : u32 { seek_set = 0, seek_current = 1, seek_end = 2 };

enum flags : u32 {
    read_only = 1, write_only = 2, read_write = 3,
    open_create = 1u << 2, open_exclusive = 1u << 3,
    open_truncate = 1u << 4, open_append = 1u << 5,
    open_access_mask = read_write,
    open_option_mask = open_create | open_exclusive | open_truncate | open_append,
    open_directory = 1u << 10,
    open_pin = 1u << 11, // explicit immutable-content lease while loading a file.
    open_valid_mask = open_access_mask | open_option_mask | open_directory | open_pin,
    list_directories = 1u << 8,
    // op::remove: permit deleting a directory (rmdir semantics). Absent — the
    // default, since every existing client zeroes the request — a directory is
    // refused before f_unlink, so rm/unlink can never delete one.
    allow_directory = 1u << 9,
};

enum class status : i32 {
    ok = 0, not_found = -1, invalid = -2, full = -3, no_space = -4,
    busy = -5, bad_handle = -6, io = -7, would_block = -8, exists = -9,
    not_directory = -10, is_directory = -11, not_empty = -12, name_too_long = -13,
    not_supported = -14, read_only_volume = -15, access_denied = -16,
};

struct [[gnu::packed]] request {
    u32 magic;
    u16 version;
    u16 operation;
    u32 request_id;
    u32 handle;
    u32 flags;
    u32 reserved;
    u64 offset;
    u32 length;
    u32 name_length;
    char name[max_name];
    u8 data[request_data_size];
};

struct [[gnu::packed]] response {
    u32 magic;
    u16 version;
    i32 status_code;
    u32 request_id;
    u32 handle;
    u32 flags;
    u32 reserved; // stat/fstat: stable per-service identity in low 16 bits.
    u64 value;
    u32 length;
    u32 name_length;
    char name[max_name];
    u8 data[response_data_size];
};

// list records are [u16 name_bytes, u8 attributes, u32 size, name_bytes].
// attributes bit 0 marks directories. The response value is the next raw entry
// index in the requested directory (zero when the listing is complete).
inline constexpr u8 entry_is_directory = 1;
inline constexpr u32 stat_is_directory = entry_is_directory;
inline constexpr u32 stat_unlinked = 1u << 1;
inline constexpr u32 stat_read_only = 1u << 2;
// op::stat/fstat: first 8 bytes of response.data carry mtime seconds (0 = unknown).
inline constexpr u32 stat_metadata_bytes = 8;
inline constexpr u32 list_record_header_size = 7;

enum metadata_mask : u16 {
    metadata_read_only = 1u << 0,
    metadata_mtime = 1u << 1,
    metadata_atime = 1u << 2,
};

struct [[gnu::packed]] metadata_request {
    u16 version; // 1
    u16 mask;
    u16 attr;    // 0 or AM_RDO
    u16 reserved;
    i64 atime_sec, atime_nsec;
    i64 mtime_sec, mtime_nsec;
};
static_assert(sizeof(metadata_request) == 40);

static_assert(sizeof(request) == message_size);
static_assert(sizeof(response) == message_size);
}
