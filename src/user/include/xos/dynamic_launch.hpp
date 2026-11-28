// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/dynamic_elf.hpp>
#include <xos/file_client.hpp>
#include <xos/launch_control.hpp>

namespace xos::dynamic {
struct approved_root { generation_root root; char manifest[128]; };
// Authority is supplied explicitly by the native controller. A generation's
// adjacent metadata never installs or approves a root.
struct launch_policy {
    u32 count, active;
    u64 sequence;
    u32 revoked, reserved;
    u8 sdk_sha256[32];
    approved_root roots[activation_max_generations];
};
struct pinned_object {
    file::client* client;
    u32 handle, size, inode;
    u32 cache_begin, cache_length;
    u8 cache[4096];
    u64 deadline;
    i64 native_error;
};
struct closure {
    generation value;
    elf_image images[generation_max_objects];
    pinned_object pins[generation_max_objects];
    pinned_object manifest_pin;
    activation_ticket ticket;
    u64 deadline;
    i64 native_error;
    bool live, quarantined;
};
bool pin_read(void* context, u64 offset, u8* destination, u32 length);
enum class controller_operation : u32 { none, open, close, metadata, read };
inline constexpr u32 controller_snapshot_version = 1;
inline constexpr u32 controller_configured = 1, controller_quarantined = 2,
    controller_uncertain = 4, controller_unknown_open = 8;
struct controller_snapshot {
    u32 version, size;
    u64 owner_pid, policy_sequence, operation_sequence, quarantine_owner_pid, deadline;
    i64 native_error;
    u32 token, retained_tokens;
    controller_operation operation;
    u32 flags;
};
static_assert(sizeof(controller_snapshot) == 72);
// Nonblocking, serialized with mutations. A competing same-process operation
// returns state and leaves output unchanged. Inspection cannot clear quarantine.
error inspect_controller(controller_snapshot& output);
bool configured();
error configure(const launch_policy& policy, u64 absolute_deadline);
// Explicitly link and enable ordinary SDK inspection/spawn routes. Programs
// which never call this keep the optional runtime out of their static image.
error install(const launch_policy& policy, u64 absolute_deadline);
error export_policy(launch_policy& policy);
error acquire(const char* path, u64 deadline, closure& result);
error acquire_index(u32 index, u64 deadline, closure& result);
// Unknown close/transport outcomes retain handle ownership and quarantine the
// closure. Callers must not recycle that storage or retry a side effect.
i64 release(closure& value);
error activate(u32 index, u64 expected_sequence, u64 deadline);
error revoke(u32 index, u64 expected_sequence);
i64 admission(void* context, u64 child, const launch::artifact& current,
              const launch::artifact& requested, u64 deadline);
}
