// SPDX-License-Identifier: Apache-2.0
#pragma once
// Test-only delivery loss AFTER production Files has performed the operation.
// This code is absent from ordinary builds. It neither changes object/storage
// rules nor offers a new guest control operation.
namespace files_uncertain_probe {
using namespace xos;
struct record { u64 pid; u32 close_handle, open_count, close_count; bool dropped; };
inline record owners[8]{};
inline bool path_is(const file::request& in, const char* path) {
    u32 i = 0;
    while (path[i]) { if (i >= in.name_length || in.name[i] != path[i]) return false; ++i; }
    return i == in.name_length;
}
inline bool drop(u32 slot, u64 pid, const file::request& in, const file::response& out) {
    if (slot >= 8) return false;
    auto& owner = owners[slot];
    if (owner.pid != pid) owner = {pid, 0, 0, 0, false};
    const auto operation = static_cast<file::op>(in.operation);
    const bool opening = operation == file::op::open && (in.flags & file::open_pin);
    bool selected = false;
    if (opening && path_is(in, "/p1b_unknown_open.bin")) { ++owner.open_count; selected = true; }
    if (opening && path_is(in, "/p1b_unknown_close.bin") && out.status_code == 0)
        owner.close_handle = out.handle;
    if (operation == file::op::close && owner.close_handle && in.handle == owner.close_handle) {
        ++owner.close_count; selected = true;
    }
    if (!selected) return false;
    sdk::print("P1B_FILES_ATTEMPT pid="); sdk::decimal(pid);
    sdk::print(" op="); sdk::decimal(in.operation);
    sdk::print(" request="); sdk::decimal(in.request_id);
    sdk::print(" count="); sdk::decimal(opening ? owner.open_count : owner.close_count);
    sdk::print(" committed="); sdk::decimal(out.status_code == 0 ? 1 : 0); sdk::print("\n");
    if (owner.dropped || out.status_code != 0) return false;
    owner.dropped = true;
    return true;
}
}
