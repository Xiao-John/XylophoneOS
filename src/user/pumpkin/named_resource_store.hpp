// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "service_core.hpp"
#include "snapshot_publication.hpp"

namespace xos::user::pumpkin {
inline constexpr usize named_resource_bytes = 32;
inline constexpr usize named_envelope_overhead = 144;
inline constexpr usize named_envelope_capacity = snapshot_capacity + named_envelope_overhead;
static_assert(named_envelope_capacity <= publication_payload_capacity);

struct named_resource_record {
    resource_key key{};
    identity_id owner{};
    u32 name_length = 0;
    u32 length = 0;
    char name[name_limit]{};
    u8 bytes[named_resource_bytes]{};
};

publication_codec named_resource_codec();

// One serialized writer holds the existing files lease and the protected
// generation authority. The resource share and account state publish as one
// unit; the account core retains its existing inner revision and format.
class named_resource_store {
public:
    named_resource_store(store_api backing, const nonce& realm) : backing_(backing), realm_(realm) {}
    named_resource_store(const named_resource_store&) = delete;
    named_resource_store& operator=(const named_resource_store&) = delete;
    store_api accounts();
    bool live() const { return !failed_; }

    status lookup(account_name name, named_resource_record& output) const;
    // These two methods are reserved for a trusted publisher. An empty
    // expected key creates a new object in a known empty resource namespace.
    status put(account_name name, const resource_key& expected, const identity_id& owner,
               const u8* bytes, usize length);
    status erase(account_name name, const resource_key& expected);

private:
    load_result load_accounts(u8* out, usize capacity, usize& length);
    replace_result replace_accounts(u64 previous, const u8* bytes, usize length);
    replace_result commit(const u8* accounts, usize length, const named_resource_record& next);

    store_api backing_;
    nonce realm_;
    u64 revision_ = 0;
    u64 account_revision_ = 0;
    usize account_length_ = 0;
    named_resource_record resource_{};
    u8 account_data_[snapshot_capacity]{};
    u8 envelope_[named_envelope_capacity]{};
    account_snapshot decoded_{};
    bool failed_ = false;
};
}
