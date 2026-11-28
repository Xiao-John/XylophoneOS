// SPDX-License-Identifier: Apache-2.0
#include "pumpkin/provisioning_protocol.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>

namespace {
using namespace xos;
using namespace xos::user::pumpkin;
constexpr nonce realm{{1, 3, 5, 7}};
struct media {
    u8 slots[2][publication_payload_capacity]{};
    usize lengths[2]{};
    generation_mark authority{};
    enum class fault { none, torn_slot, reject_publish, committed_unknown, uncommitted_unknown } failure{};
    publication_io io() {
        return {this,
            [](void* p, generation_mark& out) { out = static_cast<media*>(p)->authority;
                return out.revision ? load_result::loaded : load_result::absent; },
            [](void* p, u32 slot, u8* out, usize capacity, usize& length) {
                auto& self = *static_cast<media*>(p); length = self.lengths[slot];
                if (!length) { return load_result::absent; }
                if (length > capacity) { return load_result::io_error; }
                std::memcpy(out, self.slots[slot], length); return load_result::loaded;
            },
            [](void* p, u32 slot, const u8* data, usize length) {
                auto& self = *static_cast<media*>(p);
                self.lengths[slot] = length;
                std::memcpy(self.slots[slot], data, self.failure == fault::torn_slot ? length / 2 : length);
                return self.failure != fault::torn_slot;
            },
            [](void* p, const generation_mark& expected, const generation_mark& next) {
                auto& self = *static_cast<media*>(p);
                if (self.authority != expected) { return replace_result::conflict; }
                if (self.failure == fault::reject_publish) { return replace_result::unchanged; }
                if (self.failure != fault::uncommitted_unknown) { self.authority = next; }
                return self.failure == fault::committed_unknown || self.failure == fault::uncommitted_unknown ?
                    replace_result::outcome_unknown : replace_result::committed;
            }};
    }
};
struct fixture {
    snapshot_publication publication;
    provisioning_store store;
    service_core core;
    connection_id registrar{}, connection{};
    u64 now = 0, sequence = 0;
    u8 seed = 1;
    entropy_api entropy{&seed, [](void* p, u8* bytes, usize count) {
        for (usize i = 0; i < count; ++i) { bytes[i] = ++*static_cast<u8*>(p); }
        return true;
    }};
    explicit fixture(media& m) : publication(m.io(), realm, provisioning_codec()), store(publication.store(), realm) {}
    bool start() { return core.start(store.accounts(), realm, entropy) == status::ok &&
        core.attach(admission_role::registrar, ++now, registrar) == status::ok &&
        core.attach(admission_role::client, ++now, connection) == status::ok; }
    identity_id enroll(credential& key) {
        identity_id owner{};
        assert(core.create_account(registrar, ++now, {"alice", 5}, owner, key) == status::ok); return owner;
    }
};
catalog_candidate candidate(u64 epoch = 1, u64 sequence = 1) {
    catalog_candidate result{};
    result.catalog.count = 2; result.catalog.active = 1; result.catalog.epoch = epoch;
    result.catalog.sdk_sha256[0] = 1;
    for (u32 i = 0; i < 2; ++i) {
        auto& root = result.catalog.roots[i]; root.generation = i + 1; root.manifest_sha256[0] = i + 1;
        std::snprintf(root.manifest, sizeof(root.manifest), "/generation/%u/manifest", i + 1);
    }
    result.checkpoint.repository_id[0] = 1; result.checkpoint.key_epoch = 1;
    result.checkpoint.sequence = sequence; result.checkpoint.trusted_unix_seconds = 100;
    result.checkpoint.metadata_sha256[0] = static_cast<u8>(sequence);
    return result;
}
void transaction_cases() {
    media original;
    fixture first(original);
    assert(provision_store(first.store.accounts(), realm) == status::ok && first.start());
    credential user_key{}, app_key{}, other_key{};
    const auto owner = first.enroll(user_key);
    application_record app{}, other{};
    assert(first.store.create_application(owner, {"editor", 6}, 3, first.entropy, app, app_key) == status::ok);
    assert(first.store.create_application(owner, {"viewer", 6}, 1, first.entropy, other, other_key) == status::ok);
    assert(first.store.stage_catalog(first.store.version(), candidate()) == status::ok);
    const u8 old_data[]{'o', 'l', 'd'}, new_data[]{'n', 'e', 'w'};
    const u8 old_digest[32]{1}, new_digest[32]{2};
    assert(first.store.write_application(owner, app.number, app.authorization_epoch, app.data_revision,
        old_data, sizeof(old_data), 1, old_digest) == status::ok);
    const auto stable = original;
    for (auto fault : {media::fault::none, media::fault::torn_slot, media::fault::reject_publish,
                       media::fault::committed_unknown, media::fault::uncommitted_unknown}) {
        auto disk = stable;
        fixture live(disk); assert(live.start());
        u64 epoch = 0;
        assert(live.store.authorize_application(owner, app.number, app_key, epoch) == status::ok);
        assert(live.store.authorize_application(owner, other.number, app_key, epoch) == status::denied);
        disk.failure = fault;
        const auto result = live.store.write_application(owner, app.number, app.authorization_epoch, 2,
            new_data, sizeof(new_data), 2, new_digest);
        const bool published = fault == media::fault::none || fault == media::fault::committed_unknown;
        const bool unknown = fault == media::fault::committed_unknown || fault == media::fault::uncommitted_unknown;
        assert(result == (unknown ? status::outcome_unknown : published ? status::ok : status::io_error));
        assert(live.store.live() != unknown);
        disk.failure = media::fault::none;
        fixture recovered(disk); assert(recovered.start());
        application_record selected{};
        assert(recovered.store.read_application(owner, app.number, app.authorization_epoch, selected) == status::ok);
        assert(selected.data_revision == (published ? 3 : 2));
        assert(selected.installation_generation == (published ? 2 : 1));
        assert(!std::memcmp(selected.data, published ? new_data : old_data, 3));
        assert(!std::memcmp(selected.installation_sha256, published ? new_digest : old_digest, 32));
        if (published) {
            auto rollback = stable; rollback.authority = disk.authority;
            fixture denied(rollback); assert(!denied.start());
        }
    }
    assert(first.store.revoke_application(app.number, app.authorization_epoch) == status::ok);
    u64 epoch = 0;
    assert(first.store.authorize_application(owner, app.number, app_key, epoch) == status::denied);
    fixture after_revoke(original); assert(after_revoke.start());
    assert(after_revoke.store.authorize_application(owner, app.number, app_key, epoch) == status::denied);
    assert(after_revoke.store.revoke_generation(after_revoke.store.version(), 0) == status::ok);
    auto next = candidate(3, 2); next.catalog.revoked = 1;
    assert(after_revoke.store.stage_catalog(after_revoke.store.version(), next) == status::ok);
    auto rollback = candidate(4, 1); rollback.catalog.revoked = 1;
    assert(after_revoke.store.stage_catalog(after_revoke.store.version(), rollback) == status::denied);
    next = candidate(4, 3); // Cannot clear a historical revocation.
    assert(after_revoke.store.stage_catalog(after_revoke.store.version(), next) == status::invalid);
}
void protocol_authority() {
    media disk; fixture live(disk);
    assert(provision_store(live.store.accounts(), realm) == status::ok && live.start());
    credential login{}, app_key{}, other_key{};
    auto owner = live.enroll(login);
    application_record app{}, other{};
    assert(live.store.create_application(owner, {"editor", 6}, 3, live.entropy, app, app_key) == status::ok);
    assert(live.store.create_application(owner, {"other", 5}, 3, live.entropy, other, other_key) == status::ok);
    session_id session{};
    assert(live.core.authenticate(live.connection, ++live.now, {"alice", 5}, login, session) == status::ok);
    auto call = [&](provisioning_request request, provisioning_role role) {
        request.sequence = live.sequence + 1; request.deadline = ++live.now + max_request_ns;
        provisioning_reply reply{};
        assert(dispatch_provisioning(live.store, live.core, live.connection, role, live.sequence,
            request, live.now, live.entropy, reply)); return reply.result;
    };
    provisioning_request request{}; request.operation = provisioning_operation::read_application;
    request.session = {session.incarnation, session.number}; request.app.application = app.number;
    request.app.authorization_epoch = app.authorization_epoch; request.app.key = app_key;
    assert(call(request, provisioning_role::client) == status::ok);
    request.app.application = other.number; request.app.authorization_epoch = other.authorization_epoch;
    assert(call(request, provisioning_role::client) == status::denied);
    request.app.key = other_key; request.app.owner = owner; // claimed ownership is never authority
    assert(call(request, provisioning_role::client) == status::denied);
    request = {}; request.operation = provisioning_operation::stage_catalog;
    request.expected = live.store.version(); request.candidate = candidate();
    assert(call(request, provisioning_role::client) == status::denied);
    assert(call(request, provisioning_role::catalog_publisher) == status::ok);
    request = {}; request.operation = provisioning_operation::revoke_application;
    request.app.application = app.number; request.app.authorization_epoch = app.authorization_epoch;
    assert(call(request, provisioning_role::catalog_publisher) == status::denied);
    assert(live.core.revoke_account(live.registrar, ++live.now, owner) == status::ok);
    u64 epoch = 0;
    assert(live.store.authorize_application(owner, other.number, other_key, epoch) == status::denied);
}
void full_accounts() {
    media disk; fixture live(disk);
    assert(provision_store(live.store.accounts(), realm) == status::ok && live.start());
    for (u32 i = 0; i < account_limit; ++i) {
        char name[8]{}; const auto length = std::snprintf(name, sizeof(name), "user%u", i);
        identity_id owner{}; credential key{};
        assert(live.core.create_account(live.registrar, ++live.now, {name, static_cast<usize>(length)}, owner, key) == status::ok);
    }
    assert(disk.authority.length == provisioning_capacity);
    fixture reboot(disk); assert(reboot.start());
}
}
int main() {
    transaction_cases(); protocol_authority(); full_accounts();
    std::puts("PASS production provisioning store: torn stage, rejected CAS, committed/uncommitted unknown, exact recovery, stale disk, cross-app denial, durable revocation, catalog checkpoint, full 64-account capacity");
}
