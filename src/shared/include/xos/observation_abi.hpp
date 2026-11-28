// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>

namespace xos {
inline constexpr u64 sys_observe = 90;
}

namespace xos::observe_native {
inline constexpr u32 version = 1;
enum class query : u32 { process = 1, resources = 2, service = 3 };
enum class result : i64 {
    ok = 0, denied = -1, invalid = -2, stale = -3, deadline = -4,
    exhausted = -5, unavailable = -6,
};
enum class state : u32 { building = 1, fresh = 2, ready = 3, running = 4, waiting = 5, dead = 6 };
inline constexpr u32 flag_closing = 1, flag_service_published = 2;

// sys90(&request, &snapshot, 0). Both objects require 8-byte alignment.
// process/resources: target=0 means self, otherwise self or a direct child.
// service: target is a generic IPC endpoint held by the caller, never a PID.
// expected_* zero means no compare; other values must match after authorization.
// A nonzero finite absolute monotonic-nanosecond deadline is mandatory.
struct request {
    u32 version, size;
    query kind;
    u32 reserved;
    u64 target, expected_pid, expected_generation, deadline_ns;
};

// All unselected fields are zero. No pointer, address, credential, IPC payload,
// global resource count, child-of-child state or execution authority is exposed.
// PID and endpoint tokens do not repeat within a boot. image_generation starts
// at one for each new PID (including fork) and advances only on successful exec.
struct snapshot {
    u32 version, size;
    query kind;
    u32 flags;
    u64 observed_at_ns, completed_at_ns;
    u64 pid, parent_pid, image_generation, object_token, ticks;
    state process_state;
    u32 threads, blocked_threads, pages, page_limit;
    u32 owned_channels, channel_limit, owned_names, name_limit;
    u32 pipe_references, pipe_reference_limit, reserved;
};
static_assert(sizeof(request) == 48);
static_assert(sizeof(snapshot) == 120);
}
