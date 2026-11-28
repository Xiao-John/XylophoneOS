// SPDX-License-Identifier: Apache-2.0
#include "startup.hpp"
#include <xos/fault_sha256.hpp>

namespace xos::dynamic {
bool validate_capsule(const startup_capsule& capsule) {
    const auto& prefix = capsule.prefix;
    if (prefix.magic != XOS_DYNAMIC_STARTUP_MAGIC || prefix.version != XOS_DYNAMIC_STARTUP_VERSION
        || prefix.size != sizeof(capsule) || prefix.reserved[0] || prefix.reserved[1] || prefix.reserved[2]
        || !prefix.artifact.id || prefix.artifact.id != capsule.selected.header.id
        || !capsule.policy.count || capsule.policy.count > activation_max_generations
        || capsule.policy.active >= capsule.policy.count || capsule.policy.reserved
        || !capsule.policy.sequence || capsule.policy.revoked >> capsule.policy.count
        || validate_generation(capsule.selected) != error::none) return false;
    u8 digest[32];
    sha256 hash;
    hash.update(&capsule.selected, capsule.selected.header.size);
    hash.finish(digest);
    for (u32 i = 0; i < 32; ++i)
        if (digest[i] != prefix.artifact.sha256[i]
            || capsule.policy.sdk_sha256[i] != capsule.selected.header.sdk_sha256[i]) return false;
    bool approved = false;
    for (u32 i = 0; i < capsule.policy.count; ++i) {
        const auto& root = capsule.policy.roots[i].root;
        bool same = root.id == prefix.artifact.id && !(capsule.policy.revoked & (1u << i));
        for (u32 j = 0; j < 32; ++j) same = same && root.sha256[j] == digest[j];
        approved = approved || same;
    }
    if (!approved) return false;
    for (u32 i = 1; i < capsule.selected.header.object_count; ++i) {
        const auto& image = capsule.images[i];
        if (!capsule.pins[i].handle || !capsule.pins[i].inode || capsule.pins[i].inode > 65535
            || !image.load_count || image.load_count > elf_load_limit || !image.phnum || image.phnum > 64)
            return false;
    }
    return true;
}
}
