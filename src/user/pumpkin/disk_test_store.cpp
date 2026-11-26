// SPDX-License-Identifier: Apache-2.0
#include "disk_test_store.hpp"

namespace xos::user::pumpkin {
namespace {
constexpr char frame_magic[] = "PUMTEST1";
constexpr usize header_bytes = 16;
using user::files_private_storage::slot_bytes;
static_assert(header_bytes + snapshot_capacity <= slot_bytes);

u32 slot_for(u64 revision) {
    return static_cast<u32>((revision - 1) & 1);
}

usize frame_length(const u8* data) {
    usize length = 0;
    for (usize index = 0; index < 4; ++index) {
        length |= static_cast<usize>(data[8 + index]) << (8 * index);
    }
    return length;
}

void fill_frame(u8 (&frame)[slot_bytes], const u8* bytes, usize length) {
    wipe_bytes(frame, sizeof(frame));
    for (usize i = 0; i < sizeof(frame_magic) - 1; ++i) {
        frame[i] = static_cast<u8>(frame_magic[i]);
    }
    for (usize i = 0; i < 4; ++i) {
        frame[8 + i] = static_cast<u8>(length >> (8 * i));
    }
    __builtin_memcpy(frame + header_bytes, bytes, length);
}
}

store_api disk_test_store::api() {
    return {this,
            [](void* context, u8* data, usize capacity, usize& length) {
                return static_cast<disk_test_store*>(context)->load(data, capacity, length);
            },
            [](void* context, u64 prior, const u8* data, usize length) {
                return static_cast<disk_test_store*>(context)->replace(prior, data, length);
            }};
}

disk_test_store::selection disk_test_store::scan() {
    if (io_.read == nullptr || io_.write_and_verify == nullptr) {
        return {};
    }
    selection highest{load_result::absent, 0, 0, 0};
    u32 present = 0;
    u64 lowest = ~u64{0};
    for (u32 slot = 0; slot < 2; ++slot) {
        auto& frame = slots_[slot];
        if (!io_.read(io_.context, slot, frame)) {
            return {};
        }
        if (!has_bytes(frame, sizeof(frame))) {
            continue;
        }
        const auto length = frame_length(frame);
        if (__builtin_memcmp(frame, frame_magic, sizeof(frame_magic) - 1) != 0 ||
            has_bytes(frame + 12, 4) || length > snapshot_capacity ||
            has_bytes(frame + header_bytes + length, sizeof(frame) - header_bytes - length) ||
            !decode_snapshot(frame + header_bytes, length, disk_test_realm, parsed_) ||
            slot_for(parsed_.revision) != slot) {
            return {};
        }
        ++present;
        if (parsed_.revision < lowest) {
            lowest = parsed_.revision;
        }
        if (highest.revision < parsed_.revision) {
            highest = {load_result::loaded, slot, parsed_.revision, length};
        }
    }
    if ((present == 1 && highest.revision != 1) ||
        (present == 2 && highest.revision - lowest != 1)) {
        return {};
    }
    return highest;
}

load_result disk_test_store::load(u8* bytes, usize capacity, usize& length) {
    length = 0;
    const auto active = scan();
    if (active.result != load_result::loaded) {
        return active.result;
    }
    if (bytes == nullptr || active.length > capacity) {
        return load_result::io_error;
    }
    __builtin_memcpy(bytes, slots_[active.slot] + header_bytes, active.length);
    length = active.length;
    return load_result::loaded;
}

replace_result disk_test_store::replace(u64 previous, const u8* bytes, usize length) {
    const auto active = scan();
    if (active.result == load_result::io_error) {
        return replace_result::outcome_unknown;
    }
    if (active.revision != previous) {
        return replace_result::conflict;
    }
    if (previous == ~u64{0} || !decode_snapshot(bytes, length, disk_test_realm, parsed_) ||
        parsed_.revision != previous + 1) {
        return replace_result::unchanged;
    }
    const u32 next_slot = slot_for(parsed_.revision);
    fill_frame(slots_[next_slot], bytes, length);
    if (!io_.write_and_verify(io_.context, next_slot, slots_[next_slot])) {
        return replace_result::outcome_unknown;
    }
    const auto published = scan();
    if (published.result != load_result::loaded || published.slot != next_slot ||
        published.revision != previous + 1 || published.length != length ||
        __builtin_memcmp(slots_[published.slot] + header_bytes, bytes, length) != 0) {
        return replace_result::outcome_unknown;
    }
    return replace_result::committed;
}

}
