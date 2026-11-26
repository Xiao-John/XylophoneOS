// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "entry_stack.hpp"

namespace xos::glibc_d1 {
// A pin supplied by the already verified closure. read and context must refer
// to the same open, pinned file throughout startup. The caller owns the pin
// and must keep it live until copying completes.
struct pinned_image {
    mapped_image image;
    u64 file_size;
    elf::read_exact_fn read;
    void* context;
    image_map_budget budget;
};

struct interpreter_allocations { image_allocation main, interpreter; };
enum class interpreter_entry_error { none, layout, main_map, interpreter_map, elf_headers, stack, files };
struct interpreter_entry_result {
    interpreter_entry_error error;
    image_map_result mapping;
    i64 release_error;
};

// Prepare the actual interpreter address and ABI stack without executing it.
// Supply fresh storage on the native stack before threads or user callbacks.
// The first stack word must leave XOS_D1_STACK_GROWTH_BYTES below it.
// Success consumes the bootstrap session into frame.record.files and transfers
// both live allocations to the caller. Failures leave allocations empty. A
// nonzero rollback result requires termination of the bootstrap process.
interpreter_entry_result prepare_interpreter_entry(
    const startup_info* startup, const pinned_image& main, main_headers headers,
    const pinned_image& interpreter, execution_mode mode, entropy_source entropy,
    xos_file_session& early_files, xos_d1_entry_handoff& frame,
    interpreter_allocations& allocations, const xos_rtld_pin_plan* dependencies = nullptr);
}
