// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/types.hpp>

namespace xos::arch {
// x86 TSS bitmap: 1 denies access. The trailing all-ones byte is mandatory
// for multi-byte I/O checks at the end of the port space.
struct io_bitmap {
    static constexpr u32 port_count = 65536;
    static constexpr u32 bytes = port_count / 8;
    u8 data[bytes + 1];

    void deny_all() {
        for (u32 i = 0; i <= bytes; ++i) { data[i] = 0xff; }
    }
    bool set_range(u32 first, u32 length, bool allow) {
        if (length == 0 || first >= port_count || length > port_count - first) return false;
        for (u32 port = first; port < first + length; ++port) {
            const u8 bit = static_cast<u8>(1u << (port % 8));
            if (allow) data[port / 8] = static_cast<u8>(data[port / 8] & ~bit);
            else data[port / 8] = static_cast<u8>(data[port / 8] | bit);
        }
        return true;
    }
    bool allowed(u32 port) const {
        return port < port_count && (data[port / 8] & static_cast<u8>(1u << (port % 8))) == 0;
    }
};
static_assert(sizeof(io_bitmap) == 8193);
}
