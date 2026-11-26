// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "account_store.hpp"
#include "../services/files_private_storage.hpp"

namespace xos::user::pumpkin {

// This install realm belongs only to the disposable daemon test profile.
inline constexpr nonce disk_test_realm{{0x51, 0x70, 0x44, 0x32}};
inline constexpr char disk_test_service[] = "pumpkin-p2-test";

// The caller holds one native exclusive files lease throughout.
struct test_slot_io {
    void* context = nullptr;
    bool (*read)(void*, u32, u8 (&)[user::files_private_storage::slot_bytes]) = nullptr;
    bool (*write_and_verify)(void*, u32, const u8 (&)[user::files_private_storage::slot_bytes]) = nullptr;
};

class disk_test_store {
public:
    explicit disk_test_store(test_slot_io io) : io_(io) {}
    disk_test_store(const disk_test_store&) = delete;
    disk_test_store& operator=(const disk_test_store&) = delete;
    store_api api();

private:
    struct selection {
        load_result result = load_result::io_error;
        u32 slot = 0;
        u64 revision = 0;
        usize length = 0;
    };

    selection scan();
    load_result load(u8* bytes, usize capacity, usize& length);
    replace_result replace(u64 previous, const u8* bytes, usize length);

    test_slot_io io_;
    u8 slots_[2][user::files_private_storage::slot_bytes]{};
    account_snapshot parsed_{};
};

}
