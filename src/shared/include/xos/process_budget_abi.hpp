// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>

namespace xos {
// Explicit sys87 modes 4/5. Older kernels reject them; modes 0..3 are unchanged.
inline constexpr u32 process_budget_version = 1;
struct process_budget_vector {
    u64 processes, pages, threads, ipc_objects, names, pipes;
};
struct process_budget_config {
    u32 version, size;
    u64 reserved;
    process_budget_vector limits;
};
// Input: version, size, optional domain_id; all other fields must be zero.
// domain_id=0 selects the newest inherited domain, or returns own attribution
// with domain_id=0 when no cumulative budget has been installed.
struct process_budget_snapshot {
    u32 version, size;
    u64 domain_id, owner_pid, pid, image_generation, flags;
    process_budget_vector limits, usage, attributed;
};
inline constexpr u64 process_budget_active = 1;
static_assert(sizeof(process_budget_vector) == 48);
static_assert(sizeof(process_budget_config) == 64);
static_assert(sizeof(process_budget_snapshot) == 192);
}
