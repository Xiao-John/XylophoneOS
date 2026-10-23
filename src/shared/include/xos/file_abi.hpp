#pragma once
#include <xos/abi_types.hpp>

namespace xos::file {
// Internal E05 file-service ABI. Rebuild kernel, service, SDK and supervisor
// together; this is not a POSIX open/read/write ABI.
inline constexpr u32 request_magic = 0x51455246;  // FREQ
inline constexpr u32 response_magic = 0x53455246; // FRES
inline constexpr u16 abi_version = 1;
inline constexpr u32 message_size = 4096;
inline constexpr u32 max_name = 16;
inline constexpr u32 max_files = 4;
inline constexpr u32 max_file_bytes = 24 * 1024;
inline constexpr u32 max_open = 8;

enum class op : u16 {
    ping = 1, list = 2, stat = 3, open = 4, read = 5, write = 6, seek = 7,
    close = 8, replace_begin = 9, replace_chunk = 10, replace_commit = 11,
    replace_abort = 12, remove = 13, sync = 14,
};

enum flags : u32 { read_only = 1, write_only = 2, read_write = 3 };

enum class status : i32 {
    ok = 0, not_found = -1, invalid = -2, full = -3, no_space = -4,
    busy = -5, bad_handle = -6, io = -7, would_block = -8,
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
    u8 data[4040];
};

struct [[gnu::packed]] response {
    u32 magic;
    u16 version;
    i32 status_code;
    u32 request_id;
    u32 handle;
    u32 flags;
    u32 reserved;
    u64 value;
    u32 length;
    u32 name_length;
    char name[max_name];
    u8 data[4038];
};

static_assert(sizeof(request) == message_size);
static_assert(sizeof(response) == message_size);
}
