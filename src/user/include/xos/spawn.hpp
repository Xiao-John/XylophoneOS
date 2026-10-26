// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/process_abi.hpp>
namespace xos {
inline constexpr u64 startup_extension_magic = 0x32585445534f5855ull;
inline constexpr u32 startup_extension_offset = 64;
inline constexpr u32 startup_page_count = 4;
inline constexpr u32 startup_environment_max = 64;
// startup_info keeps its 48-byte ABI prefix. Version 2 uses reserved=64 to
// identify this extension inside the mapped startup area; pointers are user VAs.
struct startup_extension {
    u64 magic;
    u32 environment_count;
    u32 flags;
    u64 environment;
    u64 working_directory;
    u64 open_paths[3];
    u32 open_flags[3];
    u32 file_handles[3];
    u32 reserved;
};
static_assert(sizeof(startup_extension) == 88);
// v3 exec-only extension follows the compatible v2 header at offset 152.
inline constexpr u64 startup_exec_magic = 0x335845534f585546ull;
inline constexpr u32 startup_exec_offset = startup_extension_offset + sizeof(startup_extension);
enum class startup_fd_kind : u32 { kernel = 1, file = 2, pipe_read = 3, pipe_write = 4 };
struct startup_descriptor { u32 fd, object, kind, handle, flags, reserved; };
struct startup_exec_extension { u64 magic, descriptors; u32 count, reserved; };
static_assert(sizeof(startup_descriptor) == 24 && sizeof(startup_exec_extension) == 24);
namespace sdk {
struct spawn_options {
    u32 environment_count = 0;
    const char* const* environment = nullptr;
    const char* working_directory = "/";
    // -1 inherits the corresponding kernel console/pipe ref; -2 closes it.
    i64 stdio[3] = {-1, -1, -1};
    // A path here is opened by the child's libc startup, replacing that fd.
    const char* open_paths[3] = {nullptr, nullptr, nullptr};
    // Parent-session file handles are transferred to the child as references
    // to the same open description. They preserve shared offset and O_APPEND.
    u32 file_handles[3] = {0, 0, 0};
    u32 open_flags[3] = {0, 0, 0};
    // Legacy direct-child construction authority.
    bool grant_spawn = false;
    // Explicit bounded delegation. A non-supervisor may only grant a smaller
    // depth than it received; zero leaves the child unprivileged.
    u32 delegate_spawn_depth = 0;
    // Same-session descriptors are restored by the replacement's libc startup.
    // fd=UINT32_MAX requests last-object CLOEXEC cleanup before new main.
    bool replace_image = false;
    u32 exec_depth_mode = 0;
    u32 descriptor_count = 0;
    const startup_descriptor* descriptors = nullptr;
};
i64 spawn_file_options(const char* path, u32 argc, const char* const* argv,
                       const spawn_options& options);
}
}
