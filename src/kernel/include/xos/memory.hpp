// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#pragma once
#include <xos/boot_info.hpp>

namespace xos {
inline constexpr u64 page_size = 4096;
// Bootstrap cap: paging_init maps this entire identity window.
inline constexpr u64 max_managed_phys = 512ull * 1024 * 1024;

enum class memory_result : u8 {
    none,
    invalid,
    out_of_memory,
    already_mapped,
    not_mapped,
};

struct memory_stats {
    u64 usable_bytes;
    u64 managed_bytes;
    u64 low_address;
    u64 high_address;
    u32 total_pages;
    u32 free_pages;
    u32 allocated_pages;
};

struct page_permissions {
    bool writable;
    bool executable;
    bool user;
};

// Physical pages are 4 KiB, identity-accessible after paging_init, and zeroed
// when allocated. Released pages are not scrubbed.
void memory_init(const boot_info& info, const memory_region* regions);
memory_stats memory_status();
memory_result allocate_page(u64* physical);
memory_result release_page(u64 physical);

// Current kernel address space only. Intermediate tables are allocated on
// demand and never reclaimed; unmap_page frees neither tables nor physical RAM.
memory_result map_page(u64 virtual_address, u64 physical, page_permissions permissions);
memory_result unmap_page(u64 virtual_address);
memory_result query_page(u64 virtual_address, u64* physical, page_permissions* permissions);

bool memory_self_check();
const char* memory_result_name(memory_result result);

// E03 address spaces: a new PML4 shares the kernel mappings (0-64 MiB) and
// starts with an empty user half. map_page_in does not require the space to be
// active; it is used to populate a task before its first switch.
memory_result map_page_in(u64 address_space, u64 virtual_address, u64 physical,
                          page_permissions permissions);
memory_result unmap_page_in(u64 address_space, u64 virtual_address, u64* physical);
memory_result query_page_in(u64 address_space, u64 virtual_address, u64* physical,
                            page_permissions* permissions);
}

namespace xos::arch {
u64 create_address_space();
u64 destroy_address_space(u64 address_space);
void paging_init(const boot_info& info, const memory_region* regions);
}
