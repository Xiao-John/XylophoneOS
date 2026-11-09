// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/types.hpp>
namespace xos {
// A pin describes a logical user range that a suspended kernel operation may
// touch again. Its lifetime ends only after the operation completes or cancels.
struct vm_pin {
    u64 begin = 0;
    u64 end = 0;
    bool active() const { return end > begin; }
    bool set(u64 address, u64 bytes) {
        if (active() || !bytes || bytes > ~u64{0} - address) return false;
        begin = address; end = address + bytes; return true;
    }
    bool overlaps(u64 first, u64 last) const {
        return active() && first < last && begin < last && first < end;
    }
    void clear() { begin = end = 0; }
};
}
