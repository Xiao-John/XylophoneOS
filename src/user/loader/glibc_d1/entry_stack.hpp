// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/elf.hpp>
#include <xos/spawn.hpp>

namespace xos::glibc_d1 {
struct mapped_image {
    u64 bias, entry;
    const elf::segment* loads;
    u32 load_count;
};

struct main_headers {
    // From the unique verified PT_PHDR of the PIE, before the bias-dependent
    // PT_LOAD, PT_DYNAMIC and PT_INTERP entries. Both coordinates describe
    // the executable's real table.
    u64 file_offset, address;
    u32 count;
};

enum class execution_mode : u8 { ordinary, secure };
using entropy_source = bool (*)(u8* bytes, u32 size);

inline constexpr u32 entry_stack_max_words = 1 + process_max_args + 1
                                          + startup_environment_max + 1 + 2 * 9;
struct alignas(16) entry_stack {
    u64 words[entry_stack_max_words];
    u8 random[16];
};

// The bootstrap provides verified images and a policy-selected mode. This
// constructs the private x86-64 glibc stack in live native stack storage.
// It borrows strings from the mapped startup area and leaves output untouched
// on failure. Native descriptor and authority handoff are separate.
bool build_entry_stack(const startup_info* startup, const mapped_image& main,
                       main_headers headers, const mapped_image& interpreter,
                       execution_mode mode, entropy_source entropy, entry_stack& output);
}
