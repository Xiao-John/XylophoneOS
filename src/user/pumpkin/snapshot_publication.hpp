// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "account_store.hpp"

namespace xos::user::pumpkin {

struct generation_mark {
    nonce realm;
    u64 revision = 0;
    usize length = 0;
    u8 checksum[secret_bytes]{};
    bool operator==(const generation_mark&) const = default;
};

// Provided by a trusted broker holding the exclusive writer lease during
// the entire lifetime of this store. Slot writes are isolated from the
// selected slot and must be durable before write_slot returns true.
// The generation source is authoritative, including explicit absence;
// it must not be restored along with an independently replaceable data disk.
// publish_generation atomically compares the full record and durably
// installs the replacement. A zero expected record means known absence.
// It returns unchanged only if it can prove the prior record is intact.
struct publication_io {
    void* context = nullptr;
    load_result (*read_generation)(void*, generation_mark&) = nullptr;
    load_result (*read_slot)(void*, u32 slot, u8*, usize capacity, usize& length) = nullptr;
    bool (*write_slot)(void*, u32 slot, const u8*, usize length) = nullptr;
    replace_result (*publish_generation)(void*, const generation_mark& expected,
                                        const generation_mark& next) = nullptr;
};

// Private composition of storage guarantees. It neither acquires a broker
// lease nor implements the protected generation source.
class snapshot_publication {
public:
    snapshot_publication(const publication_io& io, const nonce& realm) : io_(io), realm_(realm) {}
    snapshot_publication(const snapshot_publication&) = delete;
    snapshot_publication& operator=(const snapshot_publication&) = delete;

    store_api store();

private:
    bool configured() const;
    bool describe_snapshot(const u8* bytes, usize length, generation_mark& output);
    bool verify_slot(const generation_mark& expected);
    load_result load(u8* output, usize capacity, usize& length);
    replace_result replace(u64 previous_revision, const u8* bytes, usize length);

    publication_io io_;
    nonce realm_;
    account_snapshot decoded_{};
    u8 readback_[snapshot_capacity]{};
};

}
