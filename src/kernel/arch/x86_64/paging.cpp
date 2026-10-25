#include <xos/memory.hpp>

namespace xos {
namespace {
constexpr u64 present = 1ull << 0;
constexpr u64 writable = 1ull << 1;
constexpr u64 user = 1ull << 2;
constexpr u64 huge = 1ull << 7;
constexpr u64 no_execute = 1ull << 63;
constexpr u64 address_mask = 0x000ffffffffff000ull;

u64 read_cr3() {
    u64 value;
    __asm__ volatile("mov %%cr3, %0" : "=r"(value));
    return value;
}

void flush_tlb() {
    __asm__ volatile("mov %%cr3, %%rax\n\tmov %%rax, %%cr3" : : : "rax", "memory");
}

u64* table(u64 entry) {
    return reinterpret_cast<u64*>(entry & address_mask);
}

u64 index_of(u64 address, u32 shift) {
    return (address >> shift) & 0x1ff;
}

u64* ensure_table(u64* parent, u64 index, bool user_mapping, memory_result* result) {
    if ((parent[index] & present) != 0) {
        if ((parent[index] & huge) != 0) {
            *result = memory_result::invalid;
            return nullptr;
        }
        return table(parent[index]);
    }
    u64 physical = 0;
    *result = allocate_page(&physical);
    if (*result != memory_result::none) { return nullptr; }
    parent[index] = physical | present | writable | (user_mapping ? user : 0);
    return table(physical);
}

void invalidate(u64 virtual_address) {
    __asm__ volatile("invlpg (%0)" : : "r"(virtual_address) : "memory");
}
}

memory_result map_page_in(u64 address_space, u64 virtual_address, u64 physical,
                          page_permissions permissions) {
    if ((address_space % page_size) != 0 || address_space >= max_managed_phys ||
        (virtual_address % page_size) != 0 || (physical % page_size) != 0 ||
        physical >= max_managed_phys) {
        return memory_result::invalid;
    }
    u64* pml4 = table(address_space);
    memory_result result = memory_result::none;
    u64* pdpt = ensure_table(pml4, index_of(virtual_address, 39), permissions.user, &result);
    if (pdpt == nullptr) { return result; }
    u64* pd = ensure_table(pdpt, index_of(virtual_address, 30), permissions.user, &result);
    if (pd == nullptr) { return result; }
    u64* pt = ensure_table(pd, index_of(virtual_address, 21), permissions.user, &result);
    if (pt == nullptr) { return result; }
    u64& leaf = pt[index_of(virtual_address, 12)];
    if ((leaf & present) != 0) { return memory_result::already_mapped; }
    leaf = physical | present | (permissions.writable ? writable : 0) |
           (permissions.user ? user : 0) | (permissions.executable ? 0 : no_execute);
    invalidate(virtual_address);
    return memory_result::none;
}

memory_result map_page(u64 virtual_address, u64 physical, page_permissions permissions) {
    return map_page_in(read_cr3(), virtual_address, physical, permissions);
}

memory_result unmap_page(u64 virtual_address) {
    return unmap_page_in(read_cr3(), virtual_address, nullptr);
}

memory_result unmap_page_in(u64 address_space, u64 virtual_address, u64* physical) {
    if ((address_space % page_size) != 0 || address_space >= max_managed_phys ||
        (virtual_address % page_size) != 0) { return memory_result::invalid; }
    u64* pml4 = table(address_space);
    const u64 pml4_entry = pml4[index_of(virtual_address, 39)];
    if ((pml4_entry & present) == 0 || (pml4_entry & huge) != 0) {
        return memory_result::not_mapped;
    }
    u64* pdpt = table(pml4_entry);
    const u64 pdpt_entry = pdpt[index_of(virtual_address, 30)];
    if ((pdpt_entry & present) == 0 || (pdpt_entry & huge) != 0) {
        return memory_result::not_mapped;
    }
    u64* pd = table(pdpt_entry);
    const u64 pd_entry = pd[index_of(virtual_address, 21)];
    if ((pd_entry & present) == 0) { return memory_result::not_mapped; }
    if ((pd_entry & huge) != 0) { return memory_result::invalid; }
    u64* pt = table(pd_entry);
    u64& leaf = pt[index_of(virtual_address, 12)];
    if ((leaf & present) == 0) { return memory_result::not_mapped; }
    if (physical != nullptr) { *physical = leaf & address_mask; }
    leaf = 0;
    if (read_cr3() == address_space) { invalidate(virtual_address); }
    // Thread reservations are repeatedly created/aborted in a live process.
    // Return their empty leaf tables too; the shared kernel tables stay intact.
    if (virtual_address >= 0x40000000ull && virtual_address < 0x80000000ull) {
        bool empty = true;
        for (u32 i = 0; i < 512; ++i) {
            if ((pt[i] & present) != 0) { empty = false; break; }
        }
        if (empty) {
            pd[index_of(virtual_address, 21)] = 0;
            (void)release_page(pd_entry & address_mask);
        }
    }
    return memory_result::none;
}

memory_result query_page_in(u64 address_space, u64 virtual_address, u64* physical,
                            page_permissions* permissions) {
    if (address_space == 0 || (address_space % page_size) != 0 ||
        address_space >= max_managed_phys || (virtual_address % page_size) != 0 ||
        physical == nullptr || permissions == nullptr) {
        return memory_result::invalid;
    }
    u64* pml4 = table(address_space);
    const u64 pml4_entry = pml4[index_of(virtual_address, 39)];
    if ((pml4_entry & present) == 0 || (pml4_entry & huge) != 0) {
        return memory_result::not_mapped;
    }
    u64* pdpt = table(pml4_entry);
    const u64 pdpt_entry = pdpt[index_of(virtual_address, 30)];
    if ((pdpt_entry & present) == 0 || (pdpt_entry & huge) != 0) {
        return memory_result::not_mapped;
    }
    u64* pd = table(pdpt_entry);
    const u64 pd_entry = pd[index_of(virtual_address, 21)];
    if ((pd_entry & present) == 0) { return memory_result::not_mapped; }
    if ((pd_entry & huge) != 0) { return memory_result::invalid; }
    const u64 leaf = table(pd_entry)[index_of(virtual_address, 12)];
    if ((leaf & present) == 0) { return memory_result::not_mapped; }
    *physical = leaf & address_mask;
    permissions->writable = (leaf & pd_entry & pdpt_entry & pml4_entry & writable) != 0;
    permissions->executable = ((leaf | pd_entry | pdpt_entry | pml4_entry) & no_execute) == 0;
    permissions->user = (leaf & pd_entry & pdpt_entry & pml4_entry & user) != 0;
    return memory_result::none;
}
memory_result query_page(u64 virtual_address, u64* physical, page_permissions* permissions) {
    return query_page_in(read_cr3(), virtual_address, physical, permissions);
}
}

namespace xos::arch {
u64 create_address_space() {
    u64 pml4_physical = 0;
    u64 pdpt_physical = 0;
    u64 user_pd_physical = 0;
    if (allocate_page(&pml4_physical) != memory_result::none) { return 0; }
    if (allocate_page(&pdpt_physical) != memory_result::none) {
        (void)release_page(pml4_physical);
        return 0;
    }
    if (allocate_page(&user_pd_physical) != memory_result::none) {
        (void)release_page(pdpt_physical);
        (void)release_page(pml4_physical);
        return 0;
    }
    u64* current_pml4 = table(read_cr3());
    const u64 pml4_entry = current_pml4[0];
    if ((pml4_entry & present) == 0 || (pml4_entry & huge) != 0) {
        (void)release_page(user_pd_physical);
        (void)release_page(pdpt_physical);
        (void)release_page(pml4_physical);
        return 0;
    }
    u64* current_pdpt = table(pml4_entry);
    const u64 kernel_pd_entry = current_pdpt[0];
    if ((kernel_pd_entry & present) == 0 || (kernel_pd_entry & huge) != 0) {
        (void)release_page(user_pd_physical);
        (void)release_page(pdpt_physical);
        (void)release_page(pml4_physical);
        return 0;
    }
    u64* new_pml4 = table(pml4_physical);
    u64* new_pdpt = table(pdpt_physical);
    new_pml4[0] = pdpt_physical | present | writable | user;
    new_pdpt[0] = (kernel_pd_entry & address_mask) | present | writable;
    new_pdpt[1] = user_pd_physical | present | writable | user;
    return pml4_physical;
}

u64 destroy_address_space(u64 address_space) {
    if (address_space == 0 || (address_space % page_size) != 0 || address_space >= max_managed_phys) { return 0; }
    u64 freed = 0;
    u64* pml4 = table(address_space);
    const u64 pml4_entry = pml4[0];
    if ((pml4_entry & present) == 0 || (pml4_entry & huge) != 0) { return 0; }
    u64* pdpt = table(pml4_entry);
    const u64 pdpt_entry = pdpt[1];
    if ((pdpt_entry & present) != 0 && (pdpt_entry & huge) == 0) {
        u64* pd = table(pdpt_entry);
        for (u32 i = 0; i < 512; ++i) {
            if ((pd[i] & present) == 0) { continue; }
            if ((pd[i] & huge) != 0) { continue; }
            u64* pt = table(pd[i]);
            for (u32 j = 0; j < 512; ++j) {
                if ((pt[j] & present) != 0) {
                    if (release_page(pt[j] & address_mask) == memory_result::none) { ++freed; }
                }
            }
            if (release_page(pd[i] & address_mask) == memory_result::none) { ++freed; }
        }
        if (release_page(pdpt_entry & address_mask) == memory_result::none) { ++freed; }
    }
    if (release_page(pml4_entry & address_mask) == memory_result::none) { ++freed; }
    if (release_page(address_space) == memory_result::none) { ++freed; }
    return freed;
}

void paging_init(const boot_info& info, const memory_region* regions) {
    // The loader maps 0-4 MiB with 4 KiB leaves. Extend the same identity range
    // with 2 MiB leaves so allocator pages above 4 MiB remain reachable while
    // the bootstrap has no higher-half/direct-map split yet.
    u64 highest = 4ull * 1024 * 1024;
    for (u32 i = 0; i < info.region_count; ++i) {
        if (regions[i].kind != memory_kind::usable) { continue; }
        const u64 end = regions[i].base + regions[i].length;
        if (end > highest) { highest = end; }
    }
    if (highest > max_managed_phys) { highest = max_managed_phys; }
    constexpr u64 huge_page = 2ull * 1024 * 1024;
    highest = (highest + huge_page - 1) & ~(huge_page - 1);

    u64* pml4 = table(read_cr3());
    u64* pdpt = table(pml4[0]);
    u64* pd = table(pdpt[0]);
    for (u64 address = huge_page * 2; address < highest; address += huge_page) {
        const u64 entry = address >> 21;
        if ((pd[entry] & present) == 0) {
            pd[entry] = address | present | writable | huge | no_execute;
        }
    }
    flush_tlb();
}
}
