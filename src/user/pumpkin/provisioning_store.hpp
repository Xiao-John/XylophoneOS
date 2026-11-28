// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "provisioning_types.hpp"
#include "service_core.hpp"
#include "snapshot_publication.hpp"

namespace xos::user::pumpkin {
publication_codec provisioning_codec();

// Held only by the Pumpkin owner loop. Credentials are minted by its entropy
// source, then delivered over the authenticated registrar channel. Every data
// operation checks the current persisted account and application authority.
class provisioning_store {
public:
    provisioning_store(store_api backing, const nonce& realm) : backing_(backing), realm_(realm) {}
    store_api accounts();
    bool live() const { return !failed_; }
    const nonce& realm() const { return realm_; }
    provisioning_version version() const { return {revision_, authorization_epoch_, catalog_.epoch}; }
    status checkpoint(repository_checkpoint& out, approved_catalog& catalog) const;
    status create_application(const identity_id& owner, account_name name, u32 rights,
                              const entropy_api& entropy, application_record& out, credential& key);
    status revoke_application(u64 application, u64 expected_authorization_epoch);
    status inspect_application(u64 application, application_record& out) const;
    status authorize_application(const identity_id& owner, u64 application, const credential& key,
                                 u64& epoch) const;
    status read_application(const identity_id& owner, u64 application, u64 authorization_epoch,
                            application_record& out) const;
    status write_application(const identity_id& owner, u64 application, u64 authorization_epoch,
                             u64 expected_data_revision, const u8* data, usize length,
                             u64 installation_generation, const u8 (&installation_sha256)[32]);
    status install_application(u64 application, u64 authorization_epoch, u64 expected_data_revision,
                               const u8* data, usize length, u64 installation_generation,
                               const u8 (&installation_sha256)[32]);
    // Full closure/object verification precedes this call in the trusted
    // controller. Staging writes an inactive slot; one protected CAS publishes
    // both catalog activation and repository checkpoint. No separate activation
    // can expose an uncheckpointed catalog. Unknown outcomes stop this store.
    status stage_catalog(const provisioning_version& expected, const catalog_candidate& candidate);
    status revoke_generation(const provisioning_version& expected, u32 index);
    status activate_generation(const provisioning_version& expected, u32 index);
private:
    load_result load_accounts(u8* out, usize capacity, usize& length);
    replace_result replace_accounts(u64 previous, const u8* bytes, usize length);
    replace_result commit(const u8* accounts, usize length);
    bool active_owner(const identity_id& owner) const;
    status check_application(const identity_id& owner, u64 application, u64 epoch, u32 rights) const;

    store_api backing_;
    nonce realm_;
    u64 revision_ = 0;
    u64 authorization_epoch_ = 0;
    u32 application_count_ = 0;
    usize account_length_ = 0;
    account_snapshot decoded_{};
    repository_checkpoint checkpoint_{};
    approved_catalog catalog_{};
    application_record applications_[application_limit]{};
    u8 account_data_[snapshot_capacity]{};
    u8 envelope_[provisioning_capacity]{};
    bool failed_ = false;
};
}
