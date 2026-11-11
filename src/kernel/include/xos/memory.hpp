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
// User data-page references are separate from page-table/kernel allocations.
memory_result allocate_user_page(u64* physical);
memory_result retain_user_page(u64 physical);
memory_result release_user_page(u64 physical);
u32 user_page_references(u64 physical);
struct user_page_stats { u32 unique_pages; u32 references; };
user_page_stats user_pages_status();

// Current kernel address space only. Intermediate tables are allocated on
// demand and never reclaimed; unmap_page frees neither tables nor physical RAM.
memory_result map_page(u64 virtual_address, u64 physical, page_permissions permissions);
memory_result unmap_page(u64 virtual_address);
memory_result query_page(u64 virtual_address, u64* physical, page_permissions* permissions);
memory_result query_logical_write_in(u64 address_space, u64 virtual_address, bool* result);

memory_result map_device_page(u64 virtual_address, u64 physical);
// Separate kernel-only PCI UC aperture; not an extension of the VBE mapping.
memory_result map_pci_device_page(u64 virtual_address, u64 physical);

// Kernel boot self-check only; -1 disables deterministic allocation failure.
void memory_self_test_fail_after(i64 count);
i64 memory_self_test_remaining();
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
// VM2 internal page-table primitives. A hidden committed page owns its user
// page reference but has no present user mapping. Callers own serialization.
enum class vm_page_protection : u8 { none = 0, read = 1, read_write = 3, read_execute = 5 };
memory_result vm_prepare_page_in(u64 space, u64 address);
memory_result vm_lookup_page_in(u64 space, u64 address, u64* physical, vm_page_protection* protection);
memory_result vm_install_page_in(u64 space, u64 address, u64 physical, vm_page_protection protection);
memory_result vm_protect_page_in(u64 space, u64 address, vm_page_protection protection);
memory_result vm_remove_page_in(u64 space, u64 address, u64* physical);
void vm_prune_empty_page_tables_in(u64 space, u64 address);
// Advance over one sparse page-table entry; found is a committed page.
memory_result vm_scan_page_in(u64 space, u64* cursor, u64 end, bool* found);
// Eager-copy the canonical lower user address map into an empty
// constructed address space, preserving effective user/RW/X permissions.
// Enumerates present page tables rather than probing every possible VA. On
// failure, copied_pages counts the pages already owned by destination; the
// constructor must destroy that whole unstarted space to roll back.
memory_result copy_user_pages_in(u64 source, u64 destination, u32 page_limit,
                                 u32* copied_pages);
memory_result copy_user_pages_batch(u64 source, u64 destination, u32 page_limit,
                                    u32* copied_pages, u64* cursor, u32 budget);
memory_result release_user_pages_batch(u64 space, u64* cursor, u32* released_pages, u32 budget);
}

namespace xos::arch {
u64 create_address_space();
u64 destroy_address_space(u64 address_space);
void paging_init(const boot_info& info, const memory_region* regions);
}
