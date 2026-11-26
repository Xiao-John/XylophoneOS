// SPDX-License-Identifier: Apache-2.0
#include "pumpkin/service_core.hpp"
#include "pumpkin/daemon_protocol.hpp"
#include "pumpkin/resource_dispatch.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>

using namespace xos;
using namespace xos::user::pumpkin;

namespace {

constexpr nonce realm{{1, 2, 3}};
constexpr nonce other_realm{{4, 5, 6}};

account_name name(const char* text) {
    return {text, std::strlen(text)};
}

struct memory_store {
    u8 bytes[snapshot_capacity]{};
    usize length = 0;
    u64 revision = 0;
    replace_result next = replace_result::committed;
    bool unknown_commits = false;
    bool load_fails = false;

    store_api api() {
        return {this, load, replace};
    }

    static load_result load(void* context, u8* output, usize capacity, usize& length) {
        auto& self = *static_cast<memory_store*>(context);
        if (self.load_fails) {
            return load_result::io_error;
        }
        if (self.revision == 0) {
            return load_result::absent;
        }
        assert(self.length <= capacity);
        std::memcpy(output, self.bytes, self.length);
        length = self.length;
        return load_result::loaded;
    }

    static replace_result replace(void* context, u64 previous, const u8* input, usize length) {
        auto& self = *static_cast<memory_store*>(context);
        assert(length <= sizeof(self.bytes));
        if (previous != self.revision) {
            return replace_result::conflict;
        }
        const auto result = self.next;
        self.next = replace_result::committed;
        if (result == replace_result::committed ||
            (result == replace_result::outcome_unknown && self.unknown_commits)) {
            std::memcpy(self.bytes, input, length);
            self.length = length;
            ++self.revision;
        }
        return result;
    }
};

// Predictable entropy is confined to this fixture.
struct deterministic_entropy {
    u32 counter = 1;
    bool fails = false;

    entropy_api api() {
        return {this, fill};
    }

    static bool fill(void* context, u8* output, usize size) {
        auto& self = *static_cast<deterministic_entropy*>(context);
        const u32 value = self.counter++;
        for (usize index = 0; index < size; ++index) {
            output[index] = static_cast<u8>(value + 17 * index);
        }
        return !self.fails;
    }
};

struct account {
    identity_id id;
    credential key;
};

struct fixture {
    memory_store disk;
    deterministic_entropy entropy;
    service_core core;
    connection_id registrar;

    fixture() {
        assert(provision_store(disk.api(), realm) == status::ok);
        assert(core.start(disk.api(), realm, entropy.api()) == status::ok);
        assert(core.attach(admission_role::registrar, 0, registrar) == status::ok);
    }

    connection_id client(u64 now = 0) {
        connection_id id;
        assert(core.attach(admission_role::client, now, id) == status::ok);
        return id;
    }

    account issue(const char* login, u64 now = 0) {
        account output{};
        assert(core.create_account(registrar, now, name(login), output.id, output.key) == status::ok);
        assert(has_bytes(output.key.bytes, secret_bytes));
        return output;
    }
};

void test_snapshot() {
    service_core core;
    memory_store disk;
    deterministic_entropy entropy;
    connection_id refused;
    assert(core.start(disk.api(), realm, entropy.api()) == status::not_found);
    assert(core.attach(admission_role::client, 0, refused) == status::unavailable);
    assert(disk.revision == 0);
    assert(provision_store(disk.api(), {}) == status::invalid);
    assert(provision_store(disk.api(), realm) == status::ok);
    assert(provision_store(disk.api(), other_realm) == status::conflict);
    assert(core.start(disk.api(), other_realm, entropy.api()) == status::corrupt);

    disk.load_fails = true;
    assert(core.start(disk.api(), realm, entropy.api()) == status::io_error);
    disk.load_fails = false;
    disk.bytes[8] ^= 2; // version
    assert(core.start(disk.api(), realm, entropy.api()) == status::corrupt);
    disk.bytes[8] ^= 2;
    disk.bytes[disk.length - 1] ^= 1; // checksum
    assert(core.start(disk.api(), realm, entropy.api()) == status::corrupt);
    disk.bytes[disk.length - 1] ^= 1;
    --disk.length;
    assert(core.start(disk.api(), realm, entropy.api()) == status::corrupt);
    ++disk.length;

    entropy.fails = true;
    assert(core.start(disk.api(), realm, entropy.api()) == status::io_error);
    entropy.fails = false;
    assert(core.start(disk.api(), realm, entropy.api()) == status::ok);
    assert(core.start(disk.api(), realm, entropy.api()) == status::conflict);

    fixture data;
    const auto alice = data.issue("alice");
    account_snapshot snapshot{};
    assert(decode_snapshot(data.disk.bytes, data.disk.length, realm, snapshot));
    assert(snapshot.revision == 2 && snapshot.count == 1 && alice.id.number == 1);
    assert(std::memcmp(snapshot.accounts[0].verifier, alice.key.bytes, secret_bytes) != 0);
    assert(std::memcmp(data.disk.bytes + 48 + 4 + name_limit,
                       snapshot.accounts[0].verifier, secret_bytes) == 0);
    snapshot.count = 2;
    snapshot.revision = 3;
    snapshot.accounts[1] = snapshot.accounts[0];
    u8 bytes[snapshot_capacity];
    const usize length = encode_snapshot(snapshot, bytes);
    account_snapshot rejected{};
    assert(!decode_snapshot(bytes, length, realm, rejected)); // valid checksum, duplicate name
    assert(!decode_snapshot(nullptr, length, realm, rejected));
    snapshot.count = account_limit + 1;
    assert(encode_snapshot(snapshot, bytes) == 0);
}

void test_credential_vector() {
    identity_id id{};
    id.number = 42;
    credential key{};
    for (usize index = 0; index < sizeof(id.realm.bytes); ++index) {
        id.realm.bytes[index] = static_cast<u8>(index);
    }
    for (usize index = 0; index < sizeof(key.bytes); ++index) {
        key.bytes[index] = static_cast<u8>(index);
    }
    constexpr u8 expected[] = {
        0x9d, 0x4a, 0xde, 0x87, 0xf2, 0x75, 0xcd, 0x08, 0x01, 0x75, 0xc1, 0xec,
        0x42, 0xd9, 0xc4, 0x76, 0xc2, 0x47, 0x30, 0xfb, 0xcf, 0x34, 0x42, 0xc0,
        0x36, 0x0b, 0x6b, 0x0c, 0xd6, 0x3c, 0x61, 0xb0,
    };
    u8 actual[secret_bytes];
    credential_verifier(id, key, actual);
    assert(std::memcmp(actual, expected, sizeof(expected)) == 0);
}

void test_auth_and_ownership() {
    fixture data;
    const auto first_peer = data.client();
    const auto second_peer = data.client();
    const auto alice = data.issue("alice");
    const auto bob = data.issue("b.o_b-2");
    identity_id identity = alice.id;
    credential enrollment = alice.key;
    assert(data.core.create_account(first_peer, 0, name("root"), identity, enrollment) == status::denied);
    assert(identity.number == 0 && !has_bytes(enrollment.bytes, secret_bytes));
    assert(data.core.create_account(data.registrar, 0, name("../root"), identity, enrollment) == status::invalid);
    assert(data.core.create_account(data.registrar, 0, name("Alice"), identity, enrollment) == status::invalid);
    assert(data.core.create_account(data.registrar, 0, name("alice"), identity, enrollment) == status::conflict);
    assert(data.disk.revision == 3);

    session_id first, second;
    assert(data.core.authenticate(first_peer, 0, name("alice"), bob.key, first) == status::denied);
    assert(data.core.authenticate(first_peer, 0, name("unknown"), alice.key, first) == status::denied);
    assert(first.number == 0);
    assert(data.core.authenticate(data.registrar, 0, name("alice"), alice.key, first) == status::denied);
    assert(data.core.authenticate(first_peer, 0, name("alice"), alice.key, first) == status::ok);
    assert(data.core.authenticate(first_peer, 0, name("alice"), alice.key, second) == status::conflict);
    assert(second.number == 0);
    assert(data.core.authenticate(second_peer, 0, name("b.o_b-2"), bob.key, second) == status::ok);
    assert(data.core.session_identity(first_peer, 0, first, identity) == status::ok && identity == alice.id);
    assert(data.core.session_identity(second_peer, 0, first, identity) == status::denied && identity.number == 0);

    const resource_key object{other_realm, 19, 1};
    const owner_record ownership{object, alice.id, resource_read | resource_write};
    checked_rights rights{first_peer, object, resource_read | resource_manage};
    assert(data.core.authorize_owner(first_peer, 0, first, rights, ownership, resource_read) == status::ok);
    assert(data.core.authorize_owner(first_peer, 0, first, rights, ownership, resource_write) == status::denied);
    assert(data.core.authorize_owner(first_peer, 0, first, rights, ownership, resource_manage) == status::denied);
    assert(data.core.authorize_owner(first_peer, 0, first, rights, ownership,
                                     resource_read | resource_write) == status::denied);
    assert(data.core.authorize_owner(first_peer, 0, first, rights, ownership, 0) == status::invalid);
    assert(data.core.authorize_owner(first_peer, 0, first, rights, ownership, 1u << 9) == status::invalid);
    rights.object.generation += 1;
    assert(data.core.authorize_owner(first_peer, 0, first, rights, ownership, resource_read) == status::denied);
    rights.object = object;
    rights.object.registry = realm;
    assert(data.core.authorize_owner(first_peer, 0, first, rights, ownership, resource_read) == status::denied);
    rights.object = object;
    rights.connection = second_peer;
    assert(data.core.authorize_owner(first_peer, 0, first, rights, ownership, resource_read) == status::denied);
    assert(data.core.authorize_owner(second_peer, 0, second, rights, ownership, resource_read) == status::denied);
}

void test_session_lifecycle() {
    fixture data;
    const auto alice = data.issue("alice");
    const auto first = data.client();
    const auto second = data.client();
    session_id first_session, second_session;
    identity_id identity;
    assert(data.core.authenticate(first, 0, name("alice"), alice.key, first_session) == status::ok);
    assert(data.core.logout(second, 0, first_session) == status::denied);
    assert(data.core.logout(first, 0, first_session) == status::ok);
    assert(data.core.session_identity(first, 0, first_session, identity) == status::denied);
    assert(data.core.authenticate(first, 0, name("alice"), alice.key, second_session) == status::ok);
    assert(first_session != second_session);
    assert(data.core.logout(first, 0, first_session) == status::denied);
    assert(data.core.authenticate(second, 0, name("alice"), alice.key, first_session) == status::ok);

    credential rotated;
    --data.entropy.counter; // a repeated new key must fail rotation
    assert(data.core.rotate_credential(data.registrar, 0, alice.id, rotated) == status::io_error);
    assert(data.core.session_identity(first, 0, second_session, identity) == status::ok);
    assert(!has_bytes(rotated.bytes, secret_bytes));
    assert(data.core.rotate_credential(data.registrar, 0, alice.id, rotated) == status::ok);
    assert(data.core.session_identity(first, 0, second_session, identity) == status::denied);
    assert(data.core.session_identity(second, 0, first_session, identity) == status::denied);
    assert(data.core.authenticate(first, 0, name("alice"), alice.key, first_session) == status::denied);
    assert(data.core.authenticate(first, 0, name("alice"), rotated, first_session) == status::ok);

    data.core.detach(first);
    const auto replacement = data.client();
    assert(first != replacement);
    assert(data.core.session_identity(first, 0, first_session, identity) == status::denied);
    assert(data.core.authenticate(replacement, 0, name("alice"), rotated, second_session) == status::ok);
    assert(data.core.session_identity(replacement, connection_lifetime_ns - 1, second_session, identity) ==
           status::ok);
    assert(data.core.session_identity(replacement, connection_lifetime_ns, second_session, identity) ==
           status::denied);
    assert(data.core.expire(connection_lifetime_ns - 1) == status::unavailable); // regressed clock
    connection_id refused;
    assert(data.core.attach(admission_role::client, connection_lifetime_ns, refused) == status::unavailable);
}

void test_commit_and_restart() {
    fixture data;
    const auto alice = data.issue("alice");
    const auto bob = data.issue("bob");
    const auto first = data.client();
    const auto second = data.client();
    const auto third = data.client();
    session_id alice_first, alice_second, bob_session;
    assert(data.core.authenticate(first, 0, name("alice"), alice.key, alice_first) == status::ok);
    assert(data.core.authenticate(second, 0, name("alice"), alice.key, alice_second) == status::ok);
    assert(data.core.authenticate(third, 0, name("bob"), bob.key, bob_session) == status::ok);

    identity_id observed;
    data.disk.next = replace_result::unchanged;
    assert(data.core.revoke_account(data.registrar, 0, alice.id) == status::io_error);
    assert(data.core.session_identity(first, 0, alice_first, observed) == status::ok);
    assert(data.core.revoke_account(data.registrar, 0, {other_realm, alice.id.number}) == status::not_found);
    assert(data.core.revoke_account(first, 0, alice.id) == status::denied);
    assert(data.core.revoke_account(data.registrar, 0, alice.id) == status::ok);
    assert(data.core.session_identity(first, 0, alice_first, observed) == status::denied);
    assert(data.core.session_identity(second, 0, alice_second, observed) == status::denied);
    assert(data.core.session_identity(third, 0, bob_session, observed) == status::ok);
    assert(observed == bob.id);

    service_core restarted;
    data.core.stop();
    assert(restarted.start(data.disk.api(), realm, data.entropy.api()) == status::ok);
    connection_id fresh, registrar;
    assert(restarted.attach(admission_role::client, 0, fresh) == status::ok);
    assert(restarted.attach(admission_role::registrar, 0, registrar) == status::ok);
    session_id new_session;
    assert(restarted.session_identity(third, 0, bob_session, observed) == status::denied);
    assert(restarted.authenticate(fresh, 0, name("alice"), alice.key, new_session) == status::denied);
    assert(restarted.authenticate(fresh, 0, name("bob"), bob.key, new_session) == status::ok);
    assert(restarted.session_identity(fresh, 0, bob_session, observed) == status::denied);
    assert(restarted.session_identity(fresh, 0, new_session, observed) == status::ok && observed == bob.id);
    account_description found;
    assert(restarted.lookup_account(fresh, 0, name("alice"), found) == status::denied);
    assert(restarted.lookup_account(registrar, 0, name("alice"), found) == status::ok);
    assert(found.identity == alice.id && found.disabled);
    credential key;
    assert(restarted.create_account(registrar, 0, name("alice"), observed, key) == status::conflict);
    assert(restarted.create_account(registrar, 0, name("carol"), observed, key) == status::ok);
    assert(observed.number == bob.id.number + 1);
}

void test_uncertain_storage(bool writes) {
    fixture data;
    const auto alice = data.issue("alice");
    const auto first = data.client();
    session_id session;
    assert(data.core.authenticate(first, 0, name("alice"), alice.key, session) == status::ok);

    data.disk.next = replace_result::outcome_unknown;
    data.disk.unknown_commits = writes;
    assert(data.core.revoke_account(data.registrar, 0, alice.id) == status::outcome_unknown);
    identity_id observed;
    assert(data.core.session_identity(first, 0, session, observed) == status::unavailable);
    assert(data.core.start(data.disk.api(), realm, data.entropy.api()) == status::ok);
    const auto fresh = data.client();
    const auto expected = writes ? status::denied : status::ok;
    assert(data.core.authenticate(fresh, 0, name("alice"), alice.key, session) == expected);
}

void test_lost_enrollment() {
    fixture data;
    data.disk.next = replace_result::outcome_unknown;
    data.disk.unknown_commits = true;
    account output{};
    assert(data.core.create_account(data.registrar, 0, name("alice"), output.id, output.key) ==
           status::outcome_unknown);
    assert(output.id.number == 0 && !has_bytes(output.key.bytes, secret_bytes));
    assert(data.core.start(data.disk.api(), realm, data.entropy.api()) == status::ok);
    assert(data.core.attach(admission_role::registrar, 0, data.registrar) == status::ok);
    account_description found;
    assert(data.core.lookup_account(data.registrar, 0, name("alice"), found) == status::ok);
    assert(found.identity.number == 1 && !found.disabled);
    assert(data.core.rotate_credential(data.registrar, 0, found.identity, output.key) == status::ok);
    const auto peer = data.client();
    session_id session;
    assert(data.core.authenticate(peer, 0, name("alice"), output.key, session) == status::ok);
}

void test_quotas_and_failed_enrollment() {
    fixture data;
    connection_id clients[client_limit];
    for (auto& client : clients) {
        client = data.client();
    }
    connection_id refused;
    assert(data.core.attach(admission_role::client, 0, refused) == status::exhausted);
    assert(data.core.attach(admission_role::registrar, 0, refused) == status::exhausted);
    data.core.detach(clients[0]);
    assert(data.client() != clients[0]);
    data.core.detach(data.registrar);
    assert(data.core.attach(admission_role::registrar, 0, data.registrar) == status::ok);

    account failed{};
    data.entropy.fails = true;
    assert(data.core.create_account(data.registrar, 0, name("first"), failed.id, failed.key) == status::io_error);
    assert(failed.id.number == 0 && !has_bytes(failed.key.bytes, secret_bytes) && data.disk.revision == 1);
    data.entropy.fails = false;
    data.disk.next = replace_result::unchanged;
    assert(data.core.create_account(data.registrar, 0, name("first"), failed.id, failed.key) == status::io_error);
    assert(failed.id.number == 0 && !has_bytes(failed.key.bytes, secret_bytes) && data.disk.revision == 1);

    const auto first = data.issue("first");
    assert(first.id.number == 1);
    assert(data.core.revoke_account(data.registrar, 0, first.id) == status::ok);
    for (u32 index = 1; index < account_limit; ++index) {
        char login[name_limit]{};
        std::snprintf(login, sizeof(login), "person-%u", index);
        assert(data.issue(login).id.number == index + 1);
    }
    assert(data.core.create_account(data.registrar, 0, name("overflow"), failed.id, failed.key) == status::exhausted);
    assert(data.core.create_account(data.registrar, 0, name("first"), failed.id, failed.key) == status::conflict);

    data.disk.next = replace_result::conflict;
    const identity_id last{realm, account_limit};
    assert(data.core.revoke_account(data.registrar, 0, last) == status::conflict);
    assert(data.core.attach(admission_role::client, 0, refused) == status::unavailable);
}

void test_wire_protocol() {
    fixture data;
    u64 sequence = 0;
    wire_request request;
    wire_reply reply;
    request.operation = wire_operation::create_account;
    request.name[0] = 'a';
    request.name_length = 1;
    request.deadline = 1;
    request.sequence = 1;
    request.name[1] = 'x';
    assert(!dispatch_request(data.core, data.registrar, sequence, request, 0, reply));
    request.name[1] = 0;
    request.reserved = 1;
    assert(!dispatch_request(data.core, data.registrar, sequence, request, 0, reply));
    request.reserved = 0;
    request.key.bytes[0] = 1;
    assert(!dispatch_request(data.core, data.registrar, sequence, request, 0, reply));
    request.key = {};
    assert(dispatch_request(data.core, data.registrar, sequence, request, 1, reply));
    assert(reply.result == wire_status::expired && valid_reply(request, reply));
    assert(!dispatch_request(data.core, data.registrar, sequence, request, 1, reply));
    assert(data.disk.revision == 1);
    request.sequence = 3;
    assert(!dispatch_request(data.core, data.registrar, sequence, request, 1, reply));
    assert(sequence == 1);
    request.sequence = 2;
    request.deadline = 2;
    assert(dispatch_request(data.core, data.registrar, sequence, request, 1, reply));
    assert(reply.result == wire_status::ok && valid_reply(request, reply));
    assert(data.disk.revision == 2);
    reply.flags = 1;
    assert(!valid_reply(request, reply));
    reply.flags = 0;
    reply.result = wire_status::denied;
    assert(!valid_reply(request, reply)); // extra key and token on failure
    request.sequence = 3;
    request.operation = wire_operation::lookup_account;
    assert(dispatch_request(data.core, data.registrar, sequence, request, 1, reply));
    assert(reply.result == wire_status::ok && valid_reply(request, reply) &&
           !has_bytes(reply.key.bytes, secret_bytes));
    reply.sequence++;
    assert(!valid_reply(request, reply));
    reply.sequence--;
    reply.result = static_cast<wire_status>(0xffff);
    assert(!valid_reply(request, reply));

    u32 calls = 0;
    const wire_extension login{&calls,
        [](void* context, service_core&, const connection_id&, const wire_request& incoming, u64, wire_reply& output) {
            ++*static_cast<u32*>(context);
            if (incoming.operation == wire_operation::read_login_resource) { output.flags = 17; }
            return status::ok;
        }};
    request = {};
    request.operation = wire_operation::grant_login_resource;
    request.sequence = 4;
    request.deadline = 2;
    request.token = {realm, 1};
    request.name_length = sizeof(login_resource_grant);
    assert(!dispatch_request(data.core, data.registrar, sequence, request, 1, reply));
    request.name[sizeof(login_resource_grant)] = 1;
    assert(!dispatch_request(data.core, data.registrar, sequence, request, 1, reply, &login));
    request.name[sizeof(login_resource_grant)] = 0;
    assert(dispatch_request(data.core, data.registrar, sequence, request, 2, reply, &login));
    assert(reply.result == wire_status::expired && valid_reply(request, reply) && calls == 0);
    assert(!dispatch_request(data.core, data.registrar, sequence, request, 2, reply, &login));
    request.operation = wire_operation::read_login_resource;
    request.name_length = 0;
    request.sequence = 5;
    request.deadline = 3;
    assert(dispatch_request(data.core, data.registrar, sequence, request, 2, reply, &login));
    assert(reply.result == wire_status::ok && reply.flags == 17 && valid_reply(request, reply) && calls == 1);
    reply.result = wire_status::denied;
    assert(!valid_reply(request, reply));
}

struct resource_backend {
    static constexpr u64 handle = 81;
    static constexpr u64 second_handle = 82;
    connection_id first, second;
    resource_key opened, live;
    owner_record label;
    bool labelled = true;
    u32 rights = resource_read | resource_write;
    u32 reads = 0;
    u32 writes = 0;
    u64 last_description = 0;

    resource_dispatch_io io() {
        return {
            this,
            [](void* context, const connection_id& connection, u64 supplied, resolved_resource& result) {
                auto& service = *static_cast<resource_backend*>(context);
                if (!service.labelled || (connection != service.first && connection != service.second) ||
                    (supplied != handle && supplied != second_handle)) {
                    return false;
                }
                const u64 description = supplied == handle ? 101u : 102u;
                result = {{connection, service.opened, service.rights}, service.label, description};
                return true;
            },
            [](void* context, const resource_key& object, u64 description, u32 operation) {
                auto& service = *static_cast<resource_backend*>(context);
                assert(object == service.live);
                service.last_description = description;
                if (operation == resource_read) {
                    ++service.reads;
                } else {
                    assert(operation == resource_write);
                    ++service.writes;
                }
                return status::ok;
            },
        };
    }
};

void test_resource_dispatch() {
    fixture data;
    const auto alice = data.issue("alice");
    const auto bob = data.issue("bob");
    const auto first = data.client();
    const auto second = data.client();
    session_id first_session, second_session;
    assert(data.core.authenticate(first, 0, name("alice"), alice.key, first_session) == status::ok);
    assert(data.core.authenticate(second, 0, name("bob"), bob.key, second_session) == status::ok);

    const resource_key object{other_realm, 7, 1};
    resource_backend service{first, second, object, object, {object, alice.id, resource_read}};
    const auto io = service.io();
    resource_request request{first_session, resource_backend::handle, resource_read};
    assert(dispatch_resource(data.core, first, 0, request, io) == status::ok);
    assert(service.last_description == 101);
    request.handle = resource_backend::second_handle;
    assert(dispatch_resource(data.core, first, 0, request, io) == status::ok);
    assert(service.last_description == 102);
    assert(dispatch_resource(data.core, second, 0, request, io) == status::denied); // borrowed session
    request.session = second_session;
    assert(dispatch_resource(data.core, second, 0, request, io) == status::denied); // native right, other owner
    request.session = first_session;
    request.operation = resource_write;
    assert(dispatch_resource(data.core, first, 0, request, io) == status::denied); // owner policy
    service.label.permitted |= resource_write;
    service.rights = resource_read;
    assert(dispatch_resource(data.core, first, 0, request, io) == status::denied); // object rights
    service.rights |= resource_write;
    service.labelled = false;
    assert(dispatch_resource(data.core, first, 0, request, io) == status::denied);
    service.labelled = true;
    assert(dispatch_resource(data.core, first, 0, request, io) == status::ok);

    // Reused backend slot receives a distinct object key. The previously
    // opened authority still points to the old object and can do no I/O.
    service.live.generation++;
    service.label.object = service.live;
    assert(dispatch_resource(data.core, first, 0, request, io) == status::denied);
    service.opened = service.live;
    request.handle = 99;
    assert(dispatch_resource(data.core, first, 0, request, io) == status::denied);
    request.handle = resource_backend::handle;
    assert(data.core.logout(first, 0, first_session) == status::ok);
    assert(dispatch_resource(data.core, first, 0, request, io) == status::denied);
    assert(data.core.authenticate(first, 0, name("alice"), alice.key, first_session) == status::ok);
    request.session = first_session;
    assert(dispatch_resource(data.core, first, 0, request, io) == status::ok);
    assert(data.core.revoke_account(data.registrar, 0, alice.id) == status::ok);
    assert(dispatch_resource(data.core, first, 0, request, io) == status::denied);
    request.operation = resource_read | resource_write;
    assert(dispatch_resource(data.core, first, 0, request, io) == status::invalid);
    assert(service.reads == 2 && service.writes == 2);
}

}

int main() {
    test_snapshot();
    std::puts("PASS explicit provisioning and snapshot validation");
    test_credential_vector();
    std::puts("PASS enrollment verifier digest");
    test_auth_and_ownership();
    std::puts("PASS authentication and owner-rights intersection");
    test_session_lifecycle();
    std::puts("PASS logout, credential rotation, detach and expiry");
    test_commit_and_restart();
    std::puts("PASS durable revocation and restart with stable identities");
    test_uncertain_storage(false);
    test_uncertain_storage(true);
    test_lost_enrollment();
    std::puts("PASS uncertain storage outcomes and fail-closed recovery");
    test_quotas_and_failed_enrollment();
    std::puts("PASS bounded resources and failed enrollment");
    test_wire_protocol();
    std::puts("PASS daemon protocol request, replay, deadline and reply validation");
    test_resource_dispatch();
    std::puts("PASS resource execution uses server-owned rights, labels and live sessions");
}
