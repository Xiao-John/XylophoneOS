// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/types.hpp>

namespace xos::cow {
// Architecture-independent facts supplied by a validated page-table walk.
// A hidden leaf is a committed PROT_NONE page, not an uncommitted reservation.
struct snapshot_page {
    bool present;
    bool hidden;
    bool user;
    bool parent_user;
    bool parent_writable;
    bool hardware_writable;
    bool logical_writable;
    bool executable;
    bool cow;
    u32 references;
};

enum class snapshot_action : u8 { invalid, readonly, writable_cow, hidden };

// Does not acquire references, allocate, publish, or modify either space.
// A successful caller must still retain the page and prepare an independent
// child page table before revoking the parent's hardware write permission.
constexpr snapshot_action classify_snapshot(const snapshot_page& page) {
    if (page.present == page.hidden || !page.user || !page.parent_user ||
        !page.parent_writable || page.references == 0 || page.references == ~u32{0}) {
        return snapshot_action::invalid;
    }
    if (page.hidden) {
        return (!page.hardware_writable && !page.logical_writable && !page.executable && !page.cow)
            ? snapshot_action::hidden : snapshot_action::invalid;
    }
    if (page.hardware_writable && (!page.logical_writable || page.cow || page.executable ||
                                   page.references != 1)) {
        return snapshot_action::invalid;
    }
    if (page.cow && (!page.logical_writable || page.hardware_writable || page.executable)) {
        return snapshot_action::invalid;
    }
    if (page.logical_writable) {
        return (page.hardware_writable || page.cow) && !page.executable
            ? snapshot_action::writable_cow : snapshot_action::invalid;
    }
    return page.cow ? snapshot_action::invalid : snapshot_action::readonly;
}
}
