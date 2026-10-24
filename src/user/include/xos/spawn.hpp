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
    u32 reserved;
};
static_assert(sizeof(startup_extension) == 72);
namespace sdk {
struct spawn_options {
    u32 environment_count = 0;
    const char* const* environment = nullptr;
    const char* working_directory = "/";
    // -1 inherits the corresponding kernel console/pipe ref; -2 closes it.
    i64 stdio[3] = {-1, -1, -1};
    // A path here is opened by the child's libc startup, replacing that fd.
    const char* open_paths[3] = {nullptr, nullptr, nullptr};
    u32 open_flags[3] = {0, 0, 0};
    bool grant_spawn = false;
};
i64 spawn_file_options(const char* path, u32 argc, const char* const* argv,
                       const spawn_options& options);
}
}
