// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/types.hpp>

namespace xos {
// The caller must authenticate the current principal and target relationship.
// All mutations require the scheduler's non-preemptible kernel section.
class stream_lease {
    static constexpr u32 maximum_depth = 8;
    u64 principals_[maximum_depth]{};
    u32 depth_ = 0;
    bool active_ = false;

public:
    bool active() const { return active_; }
    u64 holder() const { return depth_ == 0 ? 0 : principals_[depth_ - 1]; }
    bool contains(u64 principal) const {
        if (principal == 0) { return false; }
        for (u32 i = 0; i < depth_; ++i) {
            if (principals_[i] == principal) { return true; }
        }
        return false;
    }
    bool claim(u64 principal) {
        if (active_ || principal == 0) { return false; }
        principals_[0] = principal;
        depth_ = 1;
        active_ = true;
        return true;
    }
    bool delegate(u64 caller, u64 child) {
        if (!active_ || holder() != caller || child == 0 || contains(child) || depth_ == maximum_depth) {
            return false;
        }
        principals_[depth_++] = child;
        return true;
    }
    bool reclaim(u64 caller) {
        for (u32 i = 0; i < depth_; ++i) {
            if (principals_[i] != caller) { continue; }
            if (i + 1 < depth_) { depth_ = i + 1; return true; }
            if (i != 0) { depth_ = i; return true; }
            return false;
        }
        return false;
    }
    bool remove(u64 principal) {
        if (principal == 0) { return false; }
        for (u32 i = 0; i < depth_; ++i) {
            if (principals_[i] == principal) { depth_ = i; return true; }
        }
        return false;
    }
};
}
