// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>

namespace xos::user::pumpkin {

inline constexpr u32 account_limit = 64;
inline constexpr usize name_limit = 32;
inline constexpr usize secret_bytes = 32;
inline constexpr usize snapshot_capacity = 48 + 68 * account_limit + 32;

struct nonce {
    u8 bytes[16]{};
    bool operator==(const nonce&) const = default;
};

struct identity_id {
    nonce realm;
    u64 number = 0;
    bool operator==(const identity_id&) const = default;
};

struct account_name {
    const char* data;
    usize length;
};

struct credential {
    u8 bytes[secret_bytes]{};
};

enum class status {
    ok,
    invalid,
    denied,
    not_found,
    conflict,
    exhausted,
    unavailable,
    corrupt,
    io_error,
    outcome_unknown,
};

enum class load_result { loaded, absent, io_error };
enum class replace_result { committed, conflict, unchanged, outcome_unknown };

// The adapter owns a private, single-writer store for the whole lifetime of
// the core. Callbacks are synchronous and may not re-enter the core. A
// revision of zero means creation of a known absent store.
struct store_api {
    void* context = nullptr;
    load_result (*load)(void*, u8* output, usize capacity, usize& length) = nullptr;
    replace_result (*replace)(void*, u64 previous_revision, const u8* bytes, usize length) = nullptr;
};

struct account_record {
    char name[name_limit]{};
    u8 name_length = 0;
    bool disabled = false;
    u8 verifier[secret_bytes]{};
};

struct account_snapshot {
    nonce realm;
    u64 revision = 0;
    u32 count = 0;
    account_record accounts[account_limit]{};
};

bool valid_name(account_name name);
bool has_bytes(const u8* bytes, usize length);
void wipe_bytes(void* bytes, usize length);
void credential_verifier(const identity_id& id, const credential& key, u8 (&output)[secret_bytes]);
usize encode_snapshot(const account_snapshot& snapshot, u8 (&output)[snapshot_capacity]);
bool decode_snapshot(const u8* bytes, usize length, const nonce& expected_realm,
                     account_snapshot& output);

// Explicit provisioning. Startup never creates a new identity realm.
status provision_store(const store_api& store, const nonce& realm);

}
