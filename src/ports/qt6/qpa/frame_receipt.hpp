// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>
class QWindow;

namespace xos::qt {
// Same-process QPA query, used only on the GUI thread. This is not a kernel or
// Interactium wire ABI. Serial changes on every attempted backing-store flush.
struct frame_commit_receipt {
    u32 version, size;
    u64 serial;
    i64 result;
};
static_assert(sizeof(frame_commit_receipt) == 24);
}
extern "C" bool xos_qpa_frame_receipt(const QWindow*, xos::qt::frame_commit_receipt*);
