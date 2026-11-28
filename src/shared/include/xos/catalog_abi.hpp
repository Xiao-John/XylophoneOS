// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>

namespace xos::catalog {
inline constexpr u32 authority_version = 1;
inline constexpr u32 query_magic = 0x31514350; // PCQ1
inline constexpr u32 query_version = 1;
inline constexpr u32 root_limit = 4;
struct authority {
    u32 version = 0;
    u32 size = 0;
    u64 daemon = 0;
    u8 realm[16]{};
    char service[32]{};
    bool operator==(const authority&) const = default;
};
struct root {
    u64 generation = 0;
    u8 manifest_sha256[32]{};
    char manifest[128]{};
    bool operator==(const root&) const = default;
};
struct snapshot {
    u32 count = 0;
    u32 active = 0;
    u64 epoch = 0;
    u32 revoked = 0;
    u32 reserved = 0;
    u8 sdk_sha256[32]{};
    root roots[root_limit]{};
    bool operator==(const snapshot&) const = default;
};
struct query_request {
    u32 magic = query_magic;
    u32 version = query_version;
    u64 sequence = 0;
    u64 deadline = 0;
    u8 realm[16]{};
};
enum class query_status : u32 { ok, denied, unavailable };
struct query_reply {
    u32 magic = query_magic;
    u32 version = query_version;
    u64 sequence = 0;
    query_status status = query_status::unavailable;
    u32 reserved = 0;
    u64 revision = 0;
    u64 authorization_epoch = 0;
    u8 realm[16]{};
    snapshot catalog{};
};
static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__);
static_assert(sizeof(authority) == 64 && sizeof(root) == 168 && sizeof(snapshot) == 728);
static_assert(sizeof(query_request) == 40 && sizeof(query_reply) == 784);
inline bool authority_empty(const authority& value) {
    const auto* bytes = reinterpret_cast<const u8*>(&value);
    for (usize i = 0; i < sizeof(value); ++i) { if (bytes[i]) { return false; } }
    return true;
}
inline bool authority_valid(const authority& value) {
    if (authority_empty(value)) { return true; }
    if (value.version != authority_version || value.size != sizeof(value) || !value.daemon) { return false; }
    bool realm = false;
    for (auto byte : value.realm) { realm = realm || byte; }
    if (!realm || !value.service[0]) { return false; }
    usize end = 0;
    while (end < sizeof(value.service) && value.service[end]) {
        const auto byte = static_cast<u8>(value.service[end]);
        if (byte < 0x21 || byte > 0x7e) { return false; }
        ++end;
    }
    if (end == sizeof(value.service)) { return false; }
    for (++end; end < sizeof(value.service); ++end) { if (value.service[end]) { return false; } }
    return true;
}
}
