// SPDX-License-Identifier: Apache-2.0
#include "pumpkin/named_resource_store.hpp"

#include <cassert>
#include <cstdio>
#include <cstring>

namespace {
using namespace xos;
using namespace xos::user::pumpkin;
constexpr nonce realm{{1, 2, 3, 4}};
constexpr account_name label{"preview", 7};
constexpr u8 original_bytes[]{'o', 'n', 'e'};
constexpr u8 next_bytes[]{'t', 'w', 'o'};

struct media {
    u8 slots[2][publication_payload_capacity]{};
    usize lengths[2]{};
    generation_mark authority{};
    replace_result write_result = replace_result::committed;

    publication_io io() {
        return {this,
            [](void* context, generation_mark& mark) {
                mark = static_cast<media*>(context)->authority;
                return mark.revision ? load_result::loaded : load_result::absent;
            },
            [](void* context, u32 slot, u8* out, usize capacity, usize& length) {
                const auto& storage = *static_cast<media*>(context);
                length = storage.lengths[slot];
                if (!length) { return load_result::absent; }
                if (length > capacity) { return load_result::io_error; }
                std::memcpy(out, storage.slots[slot], length);
                return load_result::loaded;
            },
            [](void* context, u32 slot, const u8* bytes, usize length) {
                auto& storage = *static_cast<media*>(context);
                if (length > sizeof(storage.slots[slot])) { return false; }
                std::memcpy(storage.slots[slot], bytes, length);
                storage.lengths[slot] = length;
                return true;
            },
            [](void* context, const generation_mark& expected, const generation_mark& next) {
                auto& storage = *static_cast<media*>(context);
                if (storage.authority != expected) { return replace_result::conflict; }
                if (storage.write_result == replace_result::committed) { storage.authority = next; }
                return storage.write_result;
            }};
    }
};

struct system {
    snapshot_publication publication;
    named_resource_store names;
    service_core core;
    connection_id registrar{};
    u64 clock = 0;
    u8 entropy_seed;

    explicit system(media& storage, u8 seed)
        : publication(storage.io(), realm, named_resource_codec()), names(publication.store(), realm), entropy_seed(seed) {}

    bool start() {
        return core.start(names.accounts(), realm, {&entropy_seed, [](void* context, u8* bytes, usize length) {
                auto& seed = *static_cast<u8*>(context);
                for (usize i = 0; i < length; ++i) { bytes[i] = ++seed; }
                return true;
            }}) == status::ok &&
            core.attach(admission_role::registrar, ++clock, registrar) == status::ok;
    }

    identity_id create(account_name name, credential& key) {
        identity_id identity{};
        assert(core.create_account(registrar, ++clock, name, identity, key) == status::ok);
        return identity;
    }

    struct user {
        connection_id connection{};
        session_id session{};
    };

    user login(account_name name, const credential& key) {
        user result{};
        assert(core.attach(admission_role::client, ++clock, result.connection) == status::ok);
        assert(core.authenticate(result.connection, ++clock, name, key, result.session) == status::ok);
        return result;
    }

    status read(const user& actor, const named_resource_record& object, const resource_key& requested) {
        return core.authorize_owner(actor.connection, ++clock, actor.session,
            {actor.connection, requested, resource_read}, {object.key, object.owner, resource_read}, resource_read);
    }
};

void replace_and_restart() {
    media storage;
    system initial(storage, 20);
    assert(provision_store(initial.names.accounts(), realm) == status::ok && initial.start());
    credential first_key{}, second_key{};
    const auto first = initial.create({"alice", 5}, first_key);
    const auto second = initial.create({"carol", 5}, second_key);
    auto alice = initial.login({"alice", 5}, first_key);
    auto carol = initial.login({"carol", 5}, second_key);
    assert(initial.names.put(label, {}, first, original_bytes, sizeof(original_bytes)) == status::ok);
    named_resource_record old{};
    assert(initial.names.lookup(label, old) == status::ok && old.owner == first);
    assert(initial.read(alice, old, old.key) == status::ok);
    assert(initial.read(carol, old, old.key) == status::denied);
    const auto previous_media = storage;
    assert(initial.names.put(label, old.key, second, next_bytes, sizeof(next_bytes)) == status::ok);
    assert(initial.names.erase(label, old.key) == status::conflict);
    initial.core.stop();

    system rebooted(storage, 140);
    assert(rebooted.start());
    alice = rebooted.login({"alice", 5}, first_key);
    carol = rebooted.login({"carol", 5}, second_key);
    named_resource_record current{};
    assert(rebooted.names.lookup(label, current) == status::ok && current.owner == second);
    assert(old.key != current.key && current.length == sizeof(next_bytes) &&
        std::memcmp(current.bytes, next_bytes, current.length) == 0);
    assert(rebooted.read(carol, current, old.key) == status::denied);
    assert(rebooted.read(alice, current, current.key) == status::denied);
    assert(rebooted.read(carol, current, current.key) == status::ok);

    auto stale = previous_media;
    stale.authority = storage.authority;
    system historical(stale, 65);
    assert(!historical.start());

    // Account changes retain the current object and use the inner revision.
    assert(rebooted.core.revoke_account(rebooted.registrar, ++rebooted.clock, second) == status::ok);
    assert(rebooted.read(carol, current, current.key) == status::denied);
    assert(rebooted.names.erase(label, current.key) == status::ok);
    rebooted.core.stop();
    system empty(storage, 90);
    assert(empty.start());
    assert(empty.names.lookup(label, current) == status::not_found && !current.key.number);
    assert(empty.names.put(label, {}, first, original_bytes, sizeof(original_bytes)) == status::ok);
    assert(empty.names.lookup(label, current) == status::ok && current.key.generation > old.key.generation);
    assert(empty.names.erase(label, old.key) == status::conflict);
}

void capacity_and_unknown_outcome() {
    media storage;
    system current(storage, 32);
    assert(provision_store(current.names.accounts(), realm) == status::ok && current.start());
    credential key{};
    identity_id owner{};
    for (u32 i = 0; i < account_limit; ++i) {
        char name[]{'u', static_cast<char>('0' + i / 10), static_cast<char>('0' + i % 10)};
        owner = current.create({name, sizeof(name)}, key);
    }
    assert(current.names.put(label, {}, owner, next_bytes, sizeof(next_bytes)) == status::ok);
    assert(storage.authority.length == named_envelope_capacity);
    named_resource_record resource{};
    assert(current.names.lookup(label, resource) == status::ok);
    const auto committed = storage.authority;
    storage.write_result = replace_result::outcome_unknown;
    assert(current.names.erase(label, resource.key) == status::outcome_unknown && !current.names.live());
    assert(current.names.lookup(label, resource) == status::unavailable && !resource.key.number);
    assert(storage.authority == committed);
    current.core.stop();
    system after(storage, 80);
    assert(after.start() && after.names.lookup(label, resource) == status::ok && resource.owner == owner);
}
}

int main() {
    replace_and_restart();
    capacity_and_unknown_outcome();
    std::puts("PASS Pumpkin named ownership, replacement, invalidation, recovery, full capacity and outcome unknown");
}
