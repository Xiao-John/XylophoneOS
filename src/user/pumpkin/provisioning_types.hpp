// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "account_store.hpp"

namespace xos::user::pumpkin {
inline constexpr u32 application_limit = 8;
inline constexpr u32 application_data_bytes = 512;
inline constexpr u32 catalog_root_limit = 4;
inline constexpr u32 application_read = 1;
inline constexpr u32 application_write = 2;

// These are bounded, explicitly versioned service records, not kernel ABI.
struct repository_checkpoint {
    u8 repository_id[32]{};
    u64 key_epoch = 0;
    u64 sequence = 0;
    u64 trusted_unix_seconds = 0;
    u8 metadata_sha256[32]{};
    bool operator==(const repository_checkpoint&) const = default;
};
struct catalog_root {
    u64 generation = 0;
    u8 manifest_sha256[32]{};
    char manifest[128]{};
    bool operator==(const catalog_root&) const = default;
};
struct approved_catalog {
    u32 count = 0;
    u32 active = 0;
    u64 epoch = 0;
    u32 revoked = 0;
    u32 reserved = 0;
    u8 sdk_sha256[32]{};
    catalog_root roots[catalog_root_limit]{};
    bool operator==(const approved_catalog&) const = default;
};
struct application_record {
    u64 number = 0;
    u64 owner = 0;
    u64 authorization_epoch = 0;
    u64 data_revision = 0;
    u64 installation_generation = 0;
    u32 enabled = 0;
    u32 rights = 0;
    u32 data_length = 0;
    u32 name_length = 0;
    char name[name_limit]{};
    u8 verifier[secret_bytes]{};
    u8 installation_sha256[32]{};
    u8 data[application_data_bytes]{};
};
struct provisioning_version {
    u64 revision = 0;
    u64 authorization_epoch = 0;
    u64 catalog_epoch = 0;
    bool operator==(const provisioning_version&) const = default;
};
struct catalog_candidate {
    repository_checkpoint checkpoint{};
    approved_catalog catalog{};
};
static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__);
static_assert(sizeof(repository_checkpoint) == 88 && sizeof(catalog_root) == 168);
static_assert(sizeof(approved_catalog) == 728 && sizeof(application_record) == 664);
inline constexpr usize provisioning_overhead = 32 + sizeof(repository_checkpoint) +
    sizeof(approved_catalog) + application_limit * sizeof(application_record) + secret_bytes;
inline constexpr usize provisioning_capacity = snapshot_capacity + provisioning_overhead;
}
