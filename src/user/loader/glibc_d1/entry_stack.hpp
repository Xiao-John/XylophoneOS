// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "image_mapping.hpp"
#include "../../../ports/glibc/sysdeps/xos/xos_d1_start.h"
#include <xos/spawn.hpp>

namespace xos::glibc_d1 {
struct main_headers {
    // From the unique verified PT_PHDR of the PIE, before the bias-dependent
    // PT_LOAD, PT_DYNAMIC and PT_INTERP entries. Both coordinates describe
    // the executable's real table.
    u64 file_offset, address;
    u32 count;
};

enum class execution_mode : u8 { ordinary, secure };
using entropy_source = bool (*)(u8* bytes, u32 size);

inline constexpr u32 entry_stack_max_words = XOS_D1_ENTRY_WORDS;
using entry_stack = xos_d1_entry_stack;
static_assert(process_max_args == XOS_D1_MAX_ARGS);
static_assert(startup_environment_max == XOS_D1_MAX_ENVIRONMENT);

// The bootstrap provides verified images and a policy-selected mode. This
// constructs the private x86-64 glibc stack in live native stack storage.
// It borrows strings from the mapped startup area and leaves output untouched
// on failure. Native descriptor and authority handoff are separate.
bool build_entry_stack(const startup_info* startup, const mapped_image& main,
                       main_headers headers, const mapped_image& interpreter,
                       execution_mode mode, entropy_source entropy, entry_stack& output);
}
