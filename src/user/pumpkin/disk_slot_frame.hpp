// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "account_store.hpp"
#include "../services/files_private_storage.hpp"

namespace xos::user::pumpkin {

// Bound to one exclusive files lease for the lifetime of a store.
struct test_slot_io {
    void* context = nullptr;
    bool (*read)(void*, u32, u8 (&)[user::files_private_storage::slot_bytes]) = nullptr;
    bool (*write_and_verify)(void*, u32, const u8 (&)[user::files_private_storage::slot_bytes]) = nullptr;
};

namespace disk_slot_frame {

using user::files_private_storage::slot_bytes;
inline constexpr char magic[] = "PUMTEST1";
inline constexpr usize header_bytes = 16;
static_assert(header_bytes + snapshot_capacity <= slot_bytes);

inline load_result inspect(const u8 (&frame)[slot_bytes], usize& length) {
    length = 0;
    if (!has_bytes(frame, sizeof(frame))) {
        return load_result::absent;
    }
    usize size = 0;
    for (usize index = 0; index < 4; ++index) {
        size |= static_cast<usize>(frame[8 + index]) << (8 * index);
    }
    if (__builtin_memcmp(frame, magic, sizeof(magic) - 1) != 0 || has_bytes(frame + 12, 4) ||
        size > snapshot_capacity || has_bytes(frame + header_bytes + size, sizeof(frame) - header_bytes - size)) {
        return load_result::io_error;
    }
    length = size;
    return load_result::loaded;
}

inline bool encode(u8 (&frame)[slot_bytes], const u8* bytes, usize length) {
    if (bytes == nullptr || length > snapshot_capacity) {
        return false;
    }
    wipe_bytes(frame, sizeof(frame));
    __builtin_memcpy(frame, magic, sizeof(magic) - 1);
    for (usize i = 0; i < 4; ++i) {
        frame[8 + i] = static_cast<u8>(length >> (8 * i));
    }
    __builtin_memcpy(frame + header_bytes, bytes, length);
    return true;
}

}
}
