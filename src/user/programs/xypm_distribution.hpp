// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "xypm_repository_auth.hpp"
#include <xos/dynamic_elf.hpp>

namespace xypm_distribution {
struct object_source {
    char package_sha256[65]{};
    xos::u64 payload_offset = 0;
};
struct plan {
    xypm_repository_auth::release authenticated{};
    xypm_repository_auth::checkpoint next_checkpoint{};
    xos::dynamic::generation generation{};
    object_source sources[xos::dynamic::generation_max_objects]{};
    char manifest_path[128]{};
    xos::u32 package_count = 0;
};
void cleanup();
void verify(const char* repository, const char* lock,
            const xypm_repository_auth::bootstrap& trust,
            const xypm_repository_auth::checkpoint& previous,
            uint64_t trusted_unix_seconds, const xos::u8 (&sdk_identity)[32],
            bool (*canonical_path)(const char*), plan& output);
}
