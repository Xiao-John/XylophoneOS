// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/memory.hpp>
namespace xos::arch {
// Internal private-page snapshot backend, shared by runtime and diagnostics.
// Callers must freeze the source address
// space and keep the destination non-runnable until publication completes.
memory_result cow1_stage_page(u64 source, u64 destination, u64 address, i64* fail_retain = nullptr);
memory_result cow1_publish_page(u64 source, u64 destination, u64 address);
memory_result cow1_resolve_page(u64 space, u64 address);
// Cursor advances through sparse page-table entries, bounded by budget.
memory_result cow1_stage_batch(u64 source, u64 destination, u32 limit,
                               u32* staged, u64* cursor, u32 budget, i64* fail_retain = nullptr);
memory_result cow1_publish_batch(u64 source, u64 destination, u64* cursor, u32 budget);
}
