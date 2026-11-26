// SPDX-License-Identifier: Apache-2.0
#include "pumpkin/snapshot_publication.hpp"
#include "pumpkin/service_core.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <unistd.h>

using namespace xos;
using namespace xos::user::pumpkin;

namespace {
constexpr nonce realm{{0x53, 0x91}};
constexpr account_name login{"alice", 5};

enum class action { read_generation, read_selected, write_inactive, read_inactive, publish };
enum class fault { none, sync_error, staged_corrupt, unchanged, unknown_old, unknown_new };

struct fixture {
    std::FILE* slots[2]{std::tmpfile(), std::tmpfile()};
    generation_mark selected;
    fault failure = fault::none;
    action steps[32]{};
    usize step_count = 0;
    u8 entropy_counter = 0;

    fixture() {
        assert(slots[0] != nullptr && slots[1] != nullptr);
    }

    ~fixture() {
        for (auto* file : slots) {
            assert(std::fclose(file) == 0);
        }
    }

    void record(action step) {
        assert(step_count < sizeof(steps) / sizeof(steps[0]));
        steps[step_count++] = step;
    }

    void write_bytes(u32 slot, const u8* input, usize length) {
        auto* file = slots[slot];
        assert(std::fseek(file, 0, SEEK_SET) == 0);
        assert(std::fwrite(input, 1, length, file) == length);
        assert(std::fflush(file) == 0);
        assert(ftruncate(fileno(file), static_cast<off_t>(length)) == 0);
        assert(fsync(fileno(file)) == 0);
    }

    static load_result head(void* context, generation_mark& output) {
        auto& self = *static_cast<fixture*>(context);
        self.record(action::read_generation);
        output = self.selected;
        return output.revision == 0 ? load_result::absent : load_result::loaded;
    }

    static load_result read(void* context, u32 slot, u8* output, usize capacity, usize& length) {
        auto& self = *static_cast<fixture*>(context);
        assert(slot < 2);
        const auto head = self.selected.revision;
        const bool is_selected = head != 0 && slot == ((head - 1) & 1);
        self.record(is_selected ? action::read_selected : action::read_inactive);
        auto* file = self.slots[slot];
        assert(std::fseek(file, 0, SEEK_END) == 0);
        const auto length_on_disk = std::ftell(file);
        assert(length_on_disk >= 0);
        length = static_cast<usize>(length_on_disk);
        if (length == 0) {
            return load_result::absent;
        }
        assert(length <= capacity);
        assert(std::fseek(file, 0, SEEK_SET) == 0);
        assert(std::fread(output, 1, length, file) == length);
        return load_result::loaded;
    }

    static bool write(void* context, u32 slot, const u8* input, usize length) {
        auto& self = *static_cast<fixture*>(context);
        assert(slot < 2);
        assert(self.selected.revision == 0 || slot != ((self.selected.revision - 1) & 1));
        self.record(action::write_inactive);
        self.write_bytes(slot, input, length);
        if (self.failure == fault::staged_corrupt) {
            const u8 bad_byte = 0;
            assert(std::fseek(self.slots[slot], 0, SEEK_SET) == 0);
            assert(std::fwrite(&bad_byte, 1, 1, self.slots[slot]) == 1);
            assert(std::fflush(self.slots[slot]) == 0);
        }
        // A lower layer may leave the inactive slot written even when its
        // durability is uncertain. The generation must stay unchanged.
        return self.failure != fault::sync_error;
    }

    static replace_result publish(void* context, const generation_mark& expected,
                                  const generation_mark& next) {
        auto& self = *static_cast<fixture*>(context);
        self.record(action::publish);
        if (self.selected != expected) {
            return replace_result::conflict;
        }
        switch (self.failure) {
        case fault::unchanged: return replace_result::unchanged;
        case fault::unknown_old: return replace_result::outcome_unknown;
        case fault::unknown_new:
            self.selected = next;
            return replace_result::outcome_unknown;
        default:
            self.selected = next;
            return replace_result::committed;
        }
    }

    publication_io io() {
        return {this, head, read, write, publish};
    }

    entropy_api entropy() {
        return {this, [](void* context, u8* data, usize length) {
            auto& self = *static_cast<fixture*>(context);
            ++self.entropy_counter;
            for (usize index = 0; index < length; ++index) {
                data[index] = static_cast<u8>(self.entropy_counter + index);
            }
            return true;
        }};
    }
};

usize snapshot_bytes(u64 revision, u8 (&bytes)[snapshot_capacity]) {
    account_snapshot data{};
    data.realm = realm;
    data.revision = revision;
    return encode_snapshot(data, bytes);
}

void verify_loaded(const store_api& store, u64 revision) {
    u8 output[snapshot_capacity];
    usize length = 0;
    account_snapshot decoded;
    assert(store.load(store.context, output, sizeof(output), length) == load_result::loaded);
    assert(decode_snapshot(output, length, realm, decoded) && decoded.revision == revision);
}

void test_publication_order() {
    fixture backend;
    snapshot_publication publisher(backend.io(), realm);
    const auto store = publisher.store();
    assert(provision_store(store, realm) == status::ok);
    assert(backend.selected.revision == 1);
    backend.step_count = 0;
    u8 next[snapshot_capacity];
    const auto length = snapshot_bytes(2, next);
    assert(store.replace(store.context, 1, next, length) == replace_result::committed);
    constexpr action expected[]{action::read_generation, action::read_selected, action::write_inactive,
                                action::read_inactive, action::publish};
    assert(backend.step_count == sizeof(expected) / sizeof(expected[0]));
    for (usize index = 0; index < backend.step_count; ++index) {
        assert(backend.steps[index] == expected[index]);
    }
    snapshot_publication restarted(backend.io(), realm);
    verify_loaded(restarted.store(), 2);

    const auto mark = backend.selected;
    backend.step_count = 0;
    assert(store.replace(store.context, 1, next, length) == replace_result::conflict);
    assert(backend.selected == mark && backend.step_count == 2);
    assert(backend.steps[0] == action::read_generation && backend.steps[1] == action::read_selected);
}

void test_publish_failure(fault mode, replace_result result, u64 selected_revision) {
    fixture backend;
    snapshot_publication publisher(backend.io(), realm);
    const auto store = publisher.store();
    assert(provision_store(store, realm) == status::ok);
    backend.failure = mode;
    backend.step_count = 0;
    u8 next[snapshot_capacity];
    const auto length = snapshot_bytes(2, next);
    assert(store.replace(store.context, 1, next, length) == result);
    if (mode == fault::sync_error || mode == fault::staged_corrupt) {
        assert(backend.steps[backend.step_count - 1] != action::publish);
    }
    snapshot_publication restarted(backend.io(), realm);
    verify_loaded(restarted.store(), selected_revision);
}

void test_independent_generation() {
    fixture backend;
    snapshot_publication publisher(backend.io(), realm);
    const auto store = publisher.store();
    assert(provision_store(store, realm) == status::ok);
    account_snapshot account{};
    account.realm = realm;
    account.revision = 2;
    account.count = 1;
    account.accounts[0].name[0] = 'a';
    account.accounts[0].name_length = 1;
    account.accounts[0].disabled = true;
    u8 next[snapshot_capacity];
    const auto length = encode_snapshot(account, next);
    assert(store.replace(store.context, 1, next, length) == replace_result::committed);
    // Restore stale bytes only on the replaceable data medium. The protected
    // generation still points to the newer committed slot and digest.
    u8 stale[snapshot_capacity];
    const auto stale_length = snapshot_bytes(1, stale);
    backend.write_bytes(1, stale, stale_length);
    snapshot_publication restarted(backend.io(), realm);
    const auto recovered = restarted.store();
    usize loaded = 1;
    assert(recovered.load(recovered.context, stale, sizeof(stale), loaded) == load_result::io_error);
    assert(loaded == 0);
    const auto after = snapshot_bytes(3, next);
    assert(recovered.replace(recovered.context, 2, next, after) == replace_result::outcome_unknown);
    assert(backend.selected.revision == 2);

    // A second well-formed snapshot at the same revision is also rejected.
    account.accounts[0].name[0] = 'b';
    const auto different_length = encode_snapshot(account, stale);
    assert(different_length == length);
    backend.write_bytes(1, stale, different_length);
    assert(recovered.load(recovered.context, stale, sizeof(stale), loaded) == load_result::io_error);
    assert(loaded == 0 && backend.selected.revision == 2);
}

void test_identity_restart() {
    fixture backend;
    identity_id alice;
    credential key;
    {
        snapshot_publication publisher(backend.io(), realm);
        service_core core;
        assert(provision_store(publisher.store(), realm) == status::ok);
        assert(core.start(publisher.store(), realm, backend.entropy()) == status::ok);
        connection_id admin;
        assert(core.attach(admission_role::registrar, 0, admin) == status::ok);
        assert(core.create_account(admin, 0, login, alice, key) == status::ok);
    }
    {
        snapshot_publication publisher(backend.io(), realm);
        service_core core;
        assert(core.start(publisher.store(), realm, backend.entropy()) == status::ok);
        connection_id client, admin;
        assert(core.attach(admission_role::client, 0, client) == status::ok);
        session_id session;
        assert(core.authenticate(client, 0, login, key, session) == status::ok);
        identity_id observed;
        assert(core.session_identity(client, 0, session, observed) == status::ok && observed == alice);
        assert(core.attach(admission_role::registrar, 0, admin) == status::ok);
        assert(core.revoke_account(admin, 0, alice) == status::ok);
    }
    {
        snapshot_publication publisher(backend.io(), realm);
        service_core core;
        assert(core.start(publisher.store(), realm, backend.entropy()) == status::ok);
        connection_id admin, client;
        assert(core.attach(admission_role::client, 0, client) == status::ok);
        assert(core.attach(admission_role::registrar, 0, admin) == status::ok);
        account_description observed;
        assert(core.lookup_account(admin, 0, login, observed) == status::ok &&
               observed.identity == alice && observed.disabled);
        session_id session;
        assert(core.authenticate(client, 0, login, key, session) == status::denied);
    }
}
}

int main() {
    test_publication_order();
    std::puts("PASS staged write, readback, publication ordering and revision comparison");
    test_publish_failure(fault::sync_error, replace_result::unchanged, 1);
    test_publish_failure(fault::staged_corrupt, replace_result::unchanged, 1);
    test_publish_failure(fault::unchanged, replace_result::unchanged, 1);
    test_publish_failure(fault::unknown_old, replace_result::outcome_unknown, 1);
    test_publish_failure(fault::unknown_new, replace_result::outcome_unknown, 2);
    std::puts("PASS isolated stage and recoverable publish failure outcomes");
    test_independent_generation();
    std::puts("PASS stale slot rejection against separately held generation");
    test_identity_restart();
    std::puts("PASS real host file slots retain account identity and revocation");
}
