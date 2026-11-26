// SPDX-License-Identifier: Apache-2.0
#include "pumpkin/disk_test_store.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>

using namespace xos;
using namespace xos::user::pumpkin;
using user::files_private_storage::slot_bytes;

namespace {
struct disk {
    u8 slots[2][slot_bytes]{};
    u32 writes = 0;
    bool uncertain = false;
    bool damage = false;

    test_slot_io io() {
        return {this,
                [](void* context, u32 slot, u8 (&bytes)[slot_bytes]) {
                    auto& self = *static_cast<disk*>(context);
                    std::memcpy(bytes, self.slots[slot], sizeof(bytes));
                    return true;
                },
                [](void* context, u32 slot, const u8 (&bytes)[slot_bytes]) {
                    auto& self = *static_cast<disk*>(context);
                    ++self.writes;
                    std::memcpy(self.slots[slot], bytes, sizeof(bytes));
                    if (self.damage) {
                        self.slots[slot][slot_bytes - 1] ^= 1;
                    }
                    return !self.uncertain;
                }};
    }
};

usize candidate(u64 revision, u8 (&bytes)[snapshot_capacity]) {
    account_snapshot snapshot{};
    snapshot.realm = disk_test_realm;
    snapshot.revision = revision;
    return encode_snapshot(snapshot, bytes);
}

void observe(const store_api& store, u64 revision) {
    u8 bytes[snapshot_capacity]{};
    account_snapshot snapshot;
    usize length = 0;
    assert(store.load(store.context, bytes, sizeof(bytes), length) == load_result::loaded);
    assert(decode_snapshot(bytes, length, disk_test_realm, snapshot) && snapshot.revision == revision);
}
}

int main() {
    disk device;
    disk_test_store storage(device.io());
    const auto api = storage.api();
    assert(provision_store(api, disk_test_realm) == status::ok);
    assert(provision_store(api, disk_test_realm) == status::conflict);
    assert(device.writes == 1);
    u8 bytes[snapshot_capacity]{};
    usize length = candidate(2, bytes);
    assert(api.replace(api.context, 1, bytes, length) == replace_result::committed);
    assert(api.replace(api.context, 1, bytes, length) == replace_result::conflict);
    assert(device.writes == 2);
    disk_test_store restarted(device.io());
    observe(restarted.api(), 2);

    length = candidate(3, bytes);
    device.uncertain = true;
    assert(api.replace(api.context, 2, bytes, length) == replace_result::outcome_unknown);
    observe(restarted.api(), 3);
    std::puts("PASS alternating validated disk snapshots and uncertain completion");

    length = candidate(4, bytes);
    device.uncertain = false;
    device.damage = true;
    assert(api.replace(api.context, 3, bytes, length) == replace_result::outcome_unknown);
    usize loaded = 0;
    assert(restarted.api().load(restarted.api().context, bytes, sizeof(bytes), loaded) == load_result::io_error);
    assert(loaded == 0);
    std::memset(device.slots[1], 0, sizeof(device.slots[1]));
    assert(restarted.api().load(restarted.api().context, bytes, sizeof(bytes), loaded) == load_result::io_error);
    std::puts("PASS malformed or missing slot rejects fallback");
}
