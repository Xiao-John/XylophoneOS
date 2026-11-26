// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "disk_slot_frame.hpp"
#include "snapshot_publication.hpp"

namespace xos::user::pumpkin {

struct generation_record_io {
    void* context = nullptr;
    load_result (*read)(void*, generation_mark&) = nullptr;
    replace_result (*publish)(void*, const generation_mark& expected, const generation_mark& next) = nullptr;
};

// The caller provides the authenticated files lease and an independently
// protected generation endpoint. Both remain bound to this realm and its
// exclusive writer until the core and store have stopped.
class anchored_files_store {
public:
    anchored_files_store(test_slot_io slots, generation_record_io generation, const nonce& realm,
                         publication_codec codec = {});
    anchored_files_store(const anchored_files_store&) = delete;
    anchored_files_store& operator=(const anchored_files_store&) = delete;
    store_api api();

private:
    load_result read_slot(u32 slot, u8* output, usize capacity, usize& length);
    bool write_slot(u32 slot, const u8* bytes, usize length);

    test_slot_io slots_;
    generation_record_io generation_;
    usize capacity_;
    snapshot_publication publication_;
    u8 frame_[user::files_private_storage::slot_bytes]{};
};

}
