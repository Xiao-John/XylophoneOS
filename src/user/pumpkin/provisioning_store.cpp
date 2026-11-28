// SPDX-License-Identifier: Apache-2.0
#include "provisioning_store.hpp"
#include <xos/fault_sha256.hpp>

namespace xos::user::pumpkin {
namespace {
constexpr char magic[] = "PUMPROV1";
constexpr usize header_bytes = 32;
static_assert(provisioning_capacity <= publication_payload_capacity);

u64 read_le(const u8* data, usize width) {
    u64 value = 0;
    for (usize i = 0; i < width; ++i) { value |= static_cast<u64>(data[i]) << (i * 8); }
    return value;
}
void write_le(u8* data, u64 value, usize width) {
    for (usize i = 0; i < width; ++i) { data[i] = static_cast<u8>(value >> (i * 8)); }
}
void digest(const u8* data, usize length, u8* out) {
    sha256 hash;
    hash.update(data, length);
    hash.finish(out);
}
template<typename type> bool zero(const type& value) {
    return !has_bytes(reinterpret_cast<const u8*>(&value), sizeof(value));
}
bool path_valid(const char (&path)[128]) {
    if (path[0] != '/') { return false; }
    usize length = 0;
    while (length < sizeof(path) && path[length]) {
        const auto value = static_cast<u8>(path[length]);
        if (value < 0x21 || value > 0x7e || value == '\\') { return false; }
        ++length;
    }
    if (length < 2 || length == sizeof(path)) { return false; }
    for (usize i = length + 1; i < sizeof(path); ++i) { if (path[i]) { return false; } }
    for (usize start = 1; start < length;) {
        usize end = start;
        while (end < length && path[end] != '/') { ++end; }
        if (end == start || (end - start == 1 && path[start] == '.') ||
            (end - start == 2 && path[start] == '.' && path[start + 1] == '.')) { return false; }
        start = end + 1;
    }
    return path[length - 1] != '/';
}
bool catalog_valid(const approved_catalog& catalog, const repository_checkpoint& checkpoint, u64 revision) {
    if (!catalog.count) { return zero(catalog) && zero(checkpoint); }
    if (catalog.count > catalog_root_limit || !catalog.epoch || catalog.epoch > revision ||
        catalog.active >= catalog.count || catalog.reserved ||
        (catalog.revoked >> catalog.count) ||
        !has_bytes(catalog.sdk_sha256, 32) || !checkpoint.key_epoch || !checkpoint.sequence ||
        !checkpoint.trusted_unix_seconds || !has_bytes(checkpoint.repository_id, 32) ||
        !has_bytes(checkpoint.metadata_sha256, 32)) { return false; }
    for (u32 i = 0; i < catalog_root_limit; ++i) {
        const auto& root = catalog.roots[i];
        if (i >= catalog.count) { if (!zero(root)) { return false; } continue; }
        if (!root.generation || !has_bytes(root.manifest_sha256, 32) || !path_valid(root.manifest)) { return false; }
        for (u32 j = 0; j < i; ++j) {
            if (catalog.roots[j].generation == root.generation ||
                __builtin_memcmp(catalog.roots[j].manifest, root.manifest, sizeof(root.manifest)) == 0) { return false; }
        }
    }
    return true;
}
bool decode(const nonce& realm, const u8* bytes, usize length, generation_mark& mark,
            account_snapshot& accounts, u64& authorization_epoch, u32& count,
            repository_checkpoint& checkpoint, approved_catalog& catalog,
            application_record (&applications)[application_limit]) {
    if (!bytes || length < provisioning_overhead || length > provisioning_capacity ||
        __builtin_memcmp(bytes, magic, 8) != 0) { return false; }
    const u64 revision = read_le(bytes + 8, 8);
    const usize account_length = read_le(bytes + 16, 4);
    count = static_cast<u32>(read_le(bytes + 20, 4));
    authorization_epoch = read_le(bytes + 24, 8);
    if (!revision || !authorization_epoch || authorization_epoch > revision || count > application_limit ||
        account_length + provisioning_overhead != length ||
        !decode_snapshot(bytes + header_bytes, account_length, realm, accounts) || accounts.revision > revision) {
        return false;
    }
    auto* cursor = bytes + header_bytes + account_length;
    __builtin_memcpy(&checkpoint, cursor, sizeof(checkpoint)); cursor += sizeof(checkpoint);
    __builtin_memcpy(&catalog, cursor, sizeof(catalog)); cursor += sizeof(catalog);
    __builtin_memcpy(applications, cursor, sizeof(applications));
    if (!catalog_valid(catalog, checkpoint, revision)) { return false; }
    for (u32 i = 0; i < application_limit; ++i) {
        const auto& app = applications[i];
        if (i >= count) { if (!zero(app)) { return false; } continue; }
        if (app.number != i + 1 || !app.owner || app.owner > accounts.count ||
            !app.authorization_epoch || app.authorization_epoch > authorization_epoch ||
            !app.data_revision || app.data_revision > revision || app.enabled > 1 ||
            !(app.rights & application_read) || (app.rights & ~(application_read | application_write)) ||
            app.data_length > application_data_bytes || !valid_name({app.name, app.name_length}) ||
            has_bytes(reinterpret_cast<const u8*>(app.name) + app.name_length, name_limit - app.name_length) ||
            has_bytes(app.data + app.data_length, application_data_bytes - app.data_length) ||
            !has_bytes(app.verifier, secret_bytes) ||
            (app.installation_generation == 0) != !has_bytes(app.installation_sha256, 32)) { return false; }
        for (u32 j = 0; j < i; ++j) {
            if (app.owner == applications[j].owner && app.name_length == applications[j].name_length &&
                __builtin_memcmp(app.name, applications[j].name, app.name_length) == 0) { return false; }
        }
    }
    mark = {realm, revision, length, {}};
    digest(bytes, length - secret_bytes, mark.checksum);
    return __builtin_memcmp(mark.checksum, bytes + length - secret_bytes, secret_bytes) == 0;
}
status outcome(replace_result value) {
    switch (value) {
    case replace_result::committed: return status::ok;
    case replace_result::unchanged: return status::io_error;
    case replace_result::conflict: return status::conflict;
    case replace_result::outcome_unknown: return status::outcome_unknown;
    }
    return status::unavailable;
}
void application_verifier(const nonce& realm, u64 application, const credential& key, u8 (&out)[32]) {
    sha256 hash;
    constexpr char domain[] = "XOS Pumpkin application authority v1";
    hash.update(reinterpret_cast<const u8*>(domain), sizeof(domain));
    hash.update(realm.bytes, sizeof(realm.bytes));
    u8 number[8]{}; write_le(number, application, 8);
    hash.update(number, sizeof(number));
    hash.update(key.bytes, sizeof(key.bytes));
    hash.finish(out);
}
}

publication_codec provisioning_codec() {
    return {nullptr, [](void*, const nonce& realm, const u8* bytes, usize length, generation_mark& mark) {
        account_snapshot accounts{};
        repository_checkpoint checkpoint{};
        approved_catalog catalog{};
        application_record applications[application_limit]{};
        u64 epoch = 0; u32 count = 0;
        return decode(realm, bytes, length, mark, accounts, epoch, count, checkpoint, catalog, applications);
    }, provisioning_capacity};
}
store_api provisioning_store::accounts() {
    if (!backing_.load || !backing_.replace) { return {}; }
    return {this,
        [](void* context, u8* bytes, usize capacity, usize& length) {
            return static_cast<provisioning_store*>(context)->load_accounts(bytes, capacity, length);
        },
        [](void* context, u64 previous, const u8* bytes, usize length) {
            return static_cast<provisioning_store*>(context)->replace_accounts(previous, bytes, length);
        }};
}
load_result provisioning_store::load_accounts(u8* out, usize capacity, usize& length) {
    length = 0;
    if (failed_ || !out) { return load_result::io_error; }
    if (!revision_) {
        usize used = 0;
        const auto result = backing_.load(backing_.context, envelope_, sizeof(envelope_), used);
        if (result == load_result::absent) { return result; }
        generation_mark mark{};
        if (result != load_result::loaded || !decode(realm_, envelope_, used, mark, decoded_, authorization_epoch_,
            application_count_, checkpoint_, catalog_, applications_)) {
            failed_ = true; return load_result::io_error;
        }
        revision_ = mark.revision;
        account_length_ = used - provisioning_overhead;
        __builtin_memcpy(account_data_, envelope_ + header_bytes, account_length_);
    }
    if (capacity < account_length_) { return load_result::io_error; }
    __builtin_memcpy(out, account_data_, account_length_);
    length = account_length_;
    return load_result::loaded;
}
replace_result provisioning_store::replace_accounts(u64 previous, const u8* bytes, usize length) {
    if (failed_ || previous != decoded_.revision || revision_ == ~u64{0} || authorization_epoch_ == ~u64{0}) {
        return replace_result::conflict;
    }
    account_snapshot next{};
    if (!decode_snapshot(bytes, length, realm_, next) || next.revision != previous + 1) { return replace_result::unchanged; }
    const auto old_epoch = authorization_epoch_;
    ++authorization_epoch_;
    const auto result = commit(bytes, length);
    if (result == replace_result::committed) { decoded_ = next; }
    else { authorization_epoch_ = old_epoch; }
    return result;
}
replace_result provisioning_store::commit(const u8* accounts, usize length) {
    if (failed_ || !accounts || length > snapshot_capacity || revision_ == ~u64{0}) { return replace_result::unchanged; }
    const usize total = length + provisioning_overhead;
    wipe_bytes(envelope_, sizeof(envelope_));
    __builtin_memcpy(envelope_, magic, 8);
    write_le(envelope_ + 8, revision_ + 1, 8);
    write_le(envelope_ + 16, length, 4);
    write_le(envelope_ + 20, application_count_, 4);
    write_le(envelope_ + 24, authorization_epoch_, 8);
    __builtin_memcpy(envelope_ + header_bytes, accounts, length);
    auto* cursor = envelope_ + header_bytes + length;
    __builtin_memcpy(cursor, &checkpoint_, sizeof(checkpoint_)); cursor += sizeof(checkpoint_);
    __builtin_memcpy(cursor, &catalog_, sizeof(catalog_)); cursor += sizeof(catalog_);
    __builtin_memcpy(cursor, applications_, sizeof(applications_));
    digest(envelope_, total - secret_bytes, envelope_ + total - secret_bytes);
    const auto result = backing_.replace(backing_.context, revision_, envelope_, total);
    if (result == replace_result::committed) {
        ++revision_; account_length_ = length;
        __builtin_memcpy(account_data_, accounts, length);
    } else if (result != replace_result::unchanged) { failed_ = true; }
    return result;
}
bool provisioning_store::active_owner(const identity_id& owner) const {
    return owner.realm == realm_ && owner.number && owner.number <= decoded_.count &&
        !decoded_.accounts[owner.number - 1].disabled;
}
status provisioning_store::checkpoint(repository_checkpoint& out, approved_catalog& catalog) const {
    out = {}; catalog = {};
    if (failed_ || !revision_) { return status::unavailable; }
    out = checkpoint_; catalog = catalog_; return status::ok;
}
status provisioning_store::create_application(const identity_id& owner, account_name name, u32 rights,
                                               const entropy_api& entropy, application_record& out, credential& key) {
    out = {}; key = {};
    if (failed_ || !revision_) { return status::unavailable; }
    if (!active_owner(owner)) { return status::denied; }
    if (!valid_name(name) || !(rights & application_read) || (rights & ~(application_read | application_write))) {
        return status::invalid;
    }
    for (u32 i = 0; i < application_count_; ++i) {
        const auto& app = applications_[i];
        if (app.owner == owner.number && app.name_length == name.length &&
            __builtin_memcmp(app.name, name.data, name.length) == 0) { return status::conflict; }
    }
    if (application_count_ == application_limit || authorization_epoch_ == ~u64{0} || revision_ == ~u64{0}) {
        return status::exhausted;
    }
    if (!entropy.fill || !entropy.fill(entropy.context, key.bytes, sizeof(key.bytes)) || !has_bytes(key.bytes, sizeof(key.bytes))) {
        key = {}; return status::unavailable;
    }
    auto& app = applications_[application_count_];
    app = {};
    app.number = ++application_count_; app.owner = owner.number;
    app.authorization_epoch = ++authorization_epoch_; app.data_revision = 1;
    app.enabled = 1; app.rights = rights; app.name_length = static_cast<u32>(name.length);
    __builtin_memcpy(app.name, name.data, name.length);
    application_verifier(realm_, app.number, key, app.verifier);
    const auto result = commit(account_data_, account_length_);
    if (result == replace_result::committed) { out = app; return status::ok; }
    app = {}; --application_count_; --authorization_epoch_; key = {};
    return outcome(result);
}
status provisioning_store::inspect_application(u64 application, application_record& out) const {
    out = {};
    if (failed_ || !revision_) { return status::unavailable; }
    if (!application || application > application_count_) { return status::not_found; }
    out = applications_[application - 1];
    return status::ok;
}
status provisioning_store::authorize_application(const identity_id& owner, u64 application, const credential& key, u64& epoch) const {
    epoch = 0;
    if (failed_ || !revision_) { return status::unavailable; }
    if (!active_owner(owner) || !application || application > application_count_) { return status::denied; }
    const auto& app = applications_[application - 1];
    u8 verifier[32]{};
    application_verifier(realm_, application, key, verifier);
    u8 difference = 0;
    for (usize i = 0; i < sizeof(verifier); ++i) { difference |= verifier[i] ^ app.verifier[i]; }
    wipe_bytes(verifier, sizeof(verifier));
    if (difference || !app.enabled || owner.number != app.owner) { return status::denied; }
    epoch = app.authorization_epoch; return status::ok;
}
status provisioning_store::check_application(const identity_id& owner, u64 application, u64 epoch, u32 rights) const {
    if (failed_ || !revision_) { return status::unavailable; }
    if (!active_owner(owner) || !application || application > application_count_) { return status::denied; }
    const auto& app = applications_[application - 1];
    return app.enabled && app.owner == owner.number && epoch == app.authorization_epoch &&
        (app.rights & rights) == rights ? status::ok : status::denied;
}
status provisioning_store::read_application(const identity_id& owner, u64 application, u64 epoch, application_record& out) const {
    out = {};
    const auto check = check_application(owner, application, epoch, application_read);
    if (check != status::ok) { return check; }
    out = applications_[application - 1];
    // Verifiers are never exposed through the ordinary application's read API.
    wipe_bytes(out.verifier, sizeof(out.verifier));
    return status::ok;
}
status provisioning_store::write_application(const identity_id& owner, u64 application, u64 epoch,
                                             u64 previous, const u8* data, usize length,
                                             u64 installation_generation, const u8 (&installation_sha256)[32]) {
    const auto check = check_application(owner, application, epoch, application_write);
    if (check != status::ok) { return check; }
    auto& app = applications_[application - 1];
    if (previous != app.data_revision) { return status::conflict; }
    if (length > application_data_bytes || (!data && length) ||
        (installation_generation == 0) != !has_bytes(installation_sha256, 32)) { return status::invalid; }
    if (installation_generation) {
        bool approved = false;
        for (u32 i = 0; i < catalog_.count; ++i) {
            if (!(catalog_.revoked & (1u << i)) && catalog_.roots[i].generation == installation_generation &&
                __builtin_memcmp(catalog_.roots[i].manifest_sha256, installation_sha256, 32) == 0) { approved = true; }
        }
        if (!approved) { return status::denied; }
    }
    if (app.data_revision == ~u64{0} || revision_ == ~u64{0}) { return status::exhausted; }
    const auto before = app;
    ++app.data_revision; app.data_length = static_cast<u32>(length); app.installation_generation = installation_generation;
    __builtin_memcpy(app.installation_sha256, installation_sha256, 32);
    wipe_bytes(app.data, sizeof(app.data));
    if (length) { __builtin_memcpy(app.data, data, length); }
    const auto result = commit(account_data_, account_length_);
    if (result != replace_result::committed) { app = before; }
    return outcome(result);
}
status provisioning_store::revoke_application(u64 application, u64 epoch) {
    if (failed_ || !revision_) { return status::unavailable; }
    if (!application || application > application_count_) { return status::not_found; }
    auto& app = applications_[application - 1];
    if (epoch != app.authorization_epoch || !app.enabled) { return status::conflict; }
    if (authorization_epoch_ == ~u64{0} || revision_ == ~u64{0}) { return status::exhausted; }
    const auto before = app;
    app.enabled = 0; app.authorization_epoch = ++authorization_epoch_;
    const auto result = commit(account_data_, account_length_);
    if (result != replace_result::committed) { app = before; --authorization_epoch_; }
    return outcome(result);
}
status provisioning_store::install_application(u64 application, u64 epoch, u64 previous,
                                               const u8* data, usize length, u64 generation,
                                               const u8 (&sha256)[32]) {
    if (failed_ || !revision_) { return status::unavailable; }
    if (!application || application > application_count_) { return status::not_found; }
    return write_application({realm_, applications_[application - 1].owner}, application, epoch,
                              previous, data, length, generation, sha256);
}
status provisioning_store::stage_catalog(const provisioning_version& expected, const catalog_candidate& candidate) {
    if (failed_ || !revision_) { return status::unavailable; }
    if (expected != version()) { return status::conflict; }
    const auto& next = candidate.catalog;
    const auto& checkpoint = candidate.checkpoint;
    if (revision_ == ~u64{0} || catalog_.epoch == ~u64{0}) { return status::exhausted; }
    if (!next.count || !catalog_valid(next, checkpoint, revision_ + 1) ||
        (next.revoked & (1u << next.active)) || next.epoch != catalog_.epoch + 1 ||
        next.count < catalog_.count || (next.revoked & catalog_.revoked) != catalog_.revoked) { return status::invalid; }
    if (catalog_.count) {
        if (__builtin_memcmp(checkpoint.repository_id, checkpoint_.repository_id, 32) ||
            __builtin_memcmp(next.sdk_sha256, catalog_.sdk_sha256, 32) ||
            checkpoint.key_epoch < checkpoint_.key_epoch || checkpoint.sequence <= checkpoint_.sequence ||
            checkpoint.trusted_unix_seconds < checkpoint_.trusted_unix_seconds) { return status::denied; }
        for (u32 i = 0; i < catalog_.count; ++i) { if (next.roots[i] != catalog_.roots[i]) { return status::denied; } }
    }
    const auto prior_catalog = catalog_; const auto prior_checkpoint = checkpoint_;
    catalog_ = next; checkpoint_ = checkpoint;
    const auto result = commit(account_data_, account_length_);
    if (result != replace_result::committed) { catalog_ = prior_catalog; checkpoint_ = prior_checkpoint; }
    return outcome(result);
}
status provisioning_store::revoke_generation(const provisioning_version& expected, u32 index) {
    if (failed_ || !revision_) { return status::unavailable; }
    if (expected != version()) { return status::conflict; }
    if (index >= catalog_.count || (catalog_.revoked & (1u << index))) { return status::invalid; }
    if (catalog_.epoch == ~u64{0} || authorization_epoch_ == ~u64{0} || revision_ == ~u64{0}) { return status::exhausted; }
    const auto previous_active = catalog_.active;
    catalog_.revoked |= 1u << index; ++catalog_.epoch; ++authorization_epoch_;
    if (index == catalog_.active) {
        for (u32 i = 0; i < catalog_.count; ++i) {
            if (!(catalog_.revoked & (1u << i))) { catalog_.active = i; break; }
        }
    }
    const auto result = commit(account_data_, account_length_);
    if (result != replace_result::committed) {
        catalog_.active = previous_active; catalog_.revoked &= ~(1u << index);
        --catalog_.epoch; --authorization_epoch_;
    }
    return outcome(result);
}
status provisioning_store::activate_generation(const provisioning_version& expected, u32 index) {
    if (failed_ || !revision_) { return status::unavailable; }
    if (expected != version()) { return status::conflict; }
    if (index >= catalog_.count || (catalog_.revoked & (1u << index))) { return status::denied; }
    if (catalog_.epoch == ~u64{0} || revision_ == ~u64{0}) { return status::exhausted; }
    const auto previous_active = catalog_.active;
    catalog_.active = index; ++catalog_.epoch;
    const auto result = commit(account_data_, account_length_);
    if (result != replace_result::committed) { catalog_.active = previous_active; --catalog_.epoch; }
    return outcome(result);
}
}
