// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "account_store.hpp"

namespace xos::user::pumpkin {
inline constexpr u32 named_resource_bytes = 32;

struct named_resource_data {
    u32 length = 0;
    u8 bytes[named_resource_bytes]{};

    bool valid() const {
        return length && length <= sizeof(bytes) && !has_bytes(bytes + length, sizeof(bytes) - length);
    }
    bool empty() const { return !length && !has_bytes(bytes, sizeof(bytes)); }
};
static_assert(sizeof(named_resource_data) == 36);
}
