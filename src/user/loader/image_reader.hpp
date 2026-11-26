// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#pragma once

#include <xos/file_client.hpp>

namespace xos::loader {
enum class file_read_mode { probe, positioned, sequential };

// The caller owns the read-only pin and the live files session. D1 uses
// positioned mode explicitly, leaving the legacy probe for the static loader.
struct opened_file {
    file::client* client;
    u32 handle;
    u32 size;
    file_read_mode mode = file_read_mode::probe;
};

inline bool file_read(void* context, u64 offset, u8* destination, u32 length) {
    auto& source = *static_cast<opened_file*>(context);
    if (offset > source.size || length > source.size - offset ||
        (length != 0 && destination == nullptr)) {
        return false;
    }
    if (length == 0) { return true; }
    if (source.mode == file_read_mode::sequential &&
        source.client->seek(source.handle, static_cast<u32>(offset)) < 0) {
        return false;
    }
    u32 done = 0;
    while (done < length) {
        const u32 remaining = length - done;
        const u32 request_size = remaining > file::response_data_size
            ? file::response_data_size : remaining;
        i64 got;
        if (source.mode == file_read_mode::sequential) {
            got = source.client->read(source.handle, destination + done, request_size);
        } else {
            got = source.client->read_at(source.handle, destination + done, request_size, offset + done);
            if (source.mode == file_read_mode::probe) {
                source.mode = file_read_mode::positioned;
                // The previous file service used invalid for unknown operations.
                // This first request has a valid range on the held read-only pin.
                if (got == static_cast<i64>(file::status::invalid) ||
                    got == static_cast<i64>(file::status::not_supported)) {
                    source.mode = file_read_mode::sequential;
                    if (source.client->seek(source.handle, static_cast<u32>(offset)) < 0) { return false; }
                    continue;
                }
            }
        }
        if (got <= 0 || static_cast<u64>(got) > request_size) { return false; }
        done += static_cast<u32>(got);
    }
    return true;
}
}
