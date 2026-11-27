// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>

namespace xos::dynamic {
// Object and activation encodings for the offline native dynamic profile.
// They confer no process, file, device or activation authority by themselves.
inline constexpr u64 identity_magic = 0x31594e44534f5858ULL;
inline constexpr u32 identity_version = 1;
inline constexpr u32 identity_note_type = 0x584f5301;
inline constexpr u32 profile_glibc_v1 = 1;
inline constexpr u64 cpu_x86_64_baseline = 1;
enum class object_role : u32 { bootstrap = 1, interpreter = 2, main = 3, library = 4 };
struct object_identity {
    u64 magic;
    u32 version, size;
    object_role role;
    u32 machine, syscall_abi, startup_abi, libc_abi, thread_abi, tls_abi, profile;
    u64 required_cpu_features;
    u8 toolchain_abi[32];
    u8 reserved[40];
};
static_assert(sizeof(object_identity) == 128);
inline constexpr char interpreter_path[] = "/usr/lib/xos/glibc_dynamic_v1/ld_xos_x86_64.so.1";

inline constexpr u64 generation_magic = 0x314e4547534f5858ULL;
inline constexpr u32 generation_version = 1;
inline constexpr u32 generation_max_objects = 12, activation_max_generations = 4;
inline constexpr u64 generation_file_limit = 16ULL * 1024 * 1024;
inline constexpr u64 generation_bytes_limit = 64ULL * 1024 * 1024;
inline constexpr u64 generation_mapping_limit = 128ULL * 1024 * 1024;
inline constexpr u64 startup_deadline_limit_ns = 30000000000ULL;
struct generation_header {
    u64 magic;
    u32 version, size;
    u64 id;
    u32 object_count, reserved0;
    u8 sdk_sha256[32], toolchain_abi[32];
    u64 total_file_bytes, mapping_budget, startup_budget_ns, reserved1;
};
static_assert(sizeof(generation_header) == 128);
struct generation_object {
    u64 file_bytes;
    u8 sha256[32];
    object_identity identity;
    u64 bias, span;
    u32 needed_count;
    u8 needed[generation_max_objects];
    char soname[128], path[128];
    u8 reserved[56];
};
static_assert(sizeof(generation_object) == 512);
struct generation {
    generation_header header;
    generation_object objects[generation_max_objects];
};
static_assert(sizeof(generation) == 6272);
}
