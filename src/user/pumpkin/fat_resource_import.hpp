// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/file_client.hpp>
#include "named_resource_data.hpp"

namespace xos::user::pumpkin {
inline bool read_fat_resource(file::client& files, const char* path, named_resource_data& output) {
    output = {};
    u32 handle = 0, length = 0, version = 0;
    if (files.open(path, file::read_only | file::open_pin, handle, length, version) != 0) { return false; }

    // The open already selected one file object. Read its bytes through the
    // same pin even if ordinary FAT requests later replace its public name.
    named_resource_data snapshot{};
    const bool copied = length && length <= sizeof(snapshot.bytes) &&
        files.read_at(handle, snapshot.bytes, length, 0) == length;
    if (files.close(handle) != 0 || !copied) { return false; }
    snapshot.length = length;
    output = snapshot;
    return true;
}
}
