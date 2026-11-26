// SPDX-License-Identifier: Apache-2.0
#include "snapshot_publication.hpp"

namespace xos::user::pumpkin {
namespace {

u32 slot_for(u64 revision) {
    return static_cast<u32>((revision - 1) & 1);
}

}

store_api snapshot_publication::store() {
    return {
        this,
        [](void* context, u8* bytes, usize capacity, usize& length) {
            return static_cast<snapshot_publication*>(context)->load(bytes, capacity, length);
        },
        [](void* context, u64 previous, const u8* bytes, usize length) {
            return static_cast<snapshot_publication*>(context)->replace(previous, bytes, length);
        },
    };
}

bool snapshot_publication::configured() const {
    return io_.read_generation != nullptr && io_.read_slot != nullptr &&
        io_.write_slot != nullptr && io_.publish_generation != nullptr &&
        has_bytes(realm_.bytes, sizeof(realm_.bytes));
}

bool snapshot_publication::describe_snapshot(const u8* bytes, usize length, generation_mark& output) {
    if (!decode_snapshot(bytes, length, realm_, decoded_)) {
        return false;
    }
    output.realm = realm_;
    output.revision = decoded_.revision;
    output.length = length;
    for (usize index = 0; index < sizeof(output.checksum); ++index) {
        output.checksum[index] = bytes[length - sizeof(output.checksum) + index];
    }
    return true;
}

bool snapshot_publication::verify_slot(const generation_mark& expected) {
    if (expected.revision == 0 || expected.realm != realm_) {
        return false;
    }
    usize length = 0;
    if (io_.read_slot(io_.context, slot_for(expected.revision), readback_, sizeof(readback_), length) !=
            load_result::loaded ||
        length != expected.length) {
        return false;
    }
    generation_mark observed;
    return describe_snapshot(readback_, length, observed) && observed == expected;
}

load_result snapshot_publication::load(u8* output, usize capacity, usize& length) {
    length = 0;
    if (output == nullptr || !configured()) {
        return load_result::io_error;
    }
    generation_mark selected;
    const auto result = io_.read_generation(io_.context, selected);
    if (result == load_result::absent) {
        return load_result::absent;
    }
    if (result != load_result::loaded || selected.length > capacity || !verify_slot(selected)) {
        return load_result::io_error;
    }
    for (usize index = 0; index < selected.length; ++index) {
        output[index] = readback_[index];
    }
    length = selected.length;
    return load_result::loaded;
}

replace_result snapshot_publication::replace(u64 previous_revision, const u8* bytes, usize length) {
    if (!configured()) {
        return replace_result::outcome_unknown;
    }

    generation_mark next;
    if (previous_revision == ~u64{0} || !describe_snapshot(bytes, length, next) ||
        next.revision != previous_revision + 1) {
        return replace_result::unchanged;
    }

    generation_mark selected;
    const auto result = io_.read_generation(io_.context, selected);
    if (result == load_result::absent) {
        if (previous_revision != 0) {
            return replace_result::conflict;
        }
        selected = {};
    } else {
        if (result != load_result::loaded || !verify_slot(selected)) {
            return replace_result::outcome_unknown;
        }
        if (selected.revision != previous_revision) {
            return replace_result::conflict;
        }
    }

    if (!io_.write_slot(io_.context, slot_for(next.revision), bytes, length) || !verify_slot(next)) {
        // This operation only touched the unselected slot. The broker still
        // holds the writer lease and the protected generation did not move.
        return replace_result::unchanged;
    }
    return io_.publish_generation(io_.context, selected, next);
}

}
