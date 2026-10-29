// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/types.hpp>

namespace xos {
// Caller serializes all operations against the producer interrupt.  Full queues
// keep existing bytes and count discarded incoming bytes, saturating on overflow.
template <u32 capacity>
class byte_queue {
    static_assert(capacity > 0);
    u8 bytes_[capacity]{};
    u32 head_ = 0;
    u32 length_ = 0;
    u64 dropped_ = 0;

public:
    bool push(u8 value) {
        if (length_ == capacity) {
            if (dropped_ != ~u64{0}) { ++dropped_; }
            return false;
        }
        bytes_[static_cast<u32>((u64{head_} + length_) % capacity)] = value;
        ++length_;
        return true;
    }

    bool pop(u8& value) {
        if (length_ == 0) { return false; }
        value = bytes_[head_];
        head_ = (head_ + 1) % capacity;
        --length_;
        return true;
    }

    bool peek(u8& value) const {
        if (length_ == 0) { return false; }
        value = bytes_[head_];
        return true;
    }

    u32 length() const { return length_; }
    u64 dropped() const { return dropped_; }
};
}
