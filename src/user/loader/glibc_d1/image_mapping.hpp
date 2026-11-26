// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <xos/elf.hpp>

namespace xos::glibc_d1 {
inline constexpr u32 mapped_image_max_loads = 64;
struct mapped_image {
    // The entry and LOAD coordinates are relative to bias.
    u64 bias, entry;
    const elf::segment* loads;
    u32 load_count;
};

struct image_map_budget { u64 reservation_bytes, committed_bytes; };
struct image_allocation { u64 start, bytes; };
enum class image_map_error { none, layout, budget, reserve, commit, read, protect };

struct image_map_result {
    image_map_error error;
    i64 vm_error;
    // A nonzero rollback error requires termination of the bootstrap process.
    i64 rollback_error;
};

// Map a trusted, already verified layout, reading only the held object that
// supplied it. LOADs must be sorted and page-disjoint. The caller remains
// responsible for identity, ELF metadata, p_align above one page, the same
// read-only pin, relocation and RELRO. This operation is not runtime-ready.
// Call before starting another thread or running code from the image. The
// allocation must be empty and is filled only after all protections succeed.
image_map_result map_verified_image(const mapped_image& layout, u64 file_size,
                                    elf::read_exact_fn read, void* context,
                                    image_map_budget budget, image_allocation& allocation);

// Releases the whole reservation, including holes. On failure the caller
// retains the allocation and the native VM error is returned unchanged.
i64 release_image(image_allocation& allocation);
}
