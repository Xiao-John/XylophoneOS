// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#include <xos/memory.hpp>

namespace xos {
namespace {
constexpr u64 present = 1ull << 0;
constexpr u64 writable = 1ull << 1;
constexpr u64 user = 1ull << 2;
constexpr u64 huge = 1ull << 7;
// Software-owned logical write intent; independent of hardware RW.
constexpr u64 logical_writable = 1ull << 9;
constexpr u64 vm_hidden = 1ull << 10;
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
        physical >= max_managed_phys ||
        (permissions.user && (virtual_address < 0x40000000ull ||
                              virtual_address >= (1ull << 47) || user_page_references(physical) == 0))) {
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
    if ((leaf & (present | vm_hidden)) != 0) { return memory_result::already_mapped; }
    leaf = physical | present | (permissions.writable ? (writable | logical_writable) : 0) |
           (permissions.user ? user : 0) | (permissions.executable ? 0 : no_execute);
    invalidate(virtual_address);
    return memory_result::none;
}

memory_result map_device_page(u64 virtual_address, u64 physical) {
    if (virtual_address < 0x30000000ull || virtual_address >= 0x31000000ull ||
        virtual_address % page_size != 0 || physical % page_size != 0 ||
        physical < max_managed_phys || physical >= 0x100000000ull) {
        return memory_result::invalid;
    }
    u64* pdpt = table(table(read_cr3())[0]);
    u64* pd = table(pdpt[0]);
    memory_result result{};
    u64* pt = ensure_table(pd, index_of(virtual_address, 21), false, &result);
    if (pt == nullptr) { return result; }
    auto& leaf = pt[index_of(virtual_address, 12)];
    if ((leaf & present) != 0) { return memory_result::already_mapped; }
    leaf = physical | present | writable | no_execute | (1ull << 3) | (1ull << 4);
    invalidate(virtual_address);
    return memory_result::none;
}

memory_result map_pci_device_page(u64 virtual_address, u64 physical) {
    if (virtual_address < 0x32000000ull || virtual_address >= 0x33000000ull ||
        virtual_address % page_size != 0 || physical % page_size != 0 ||
        physical < max_managed_phys || physical >= 0x100000000ull) {
        return memory_result::invalid;
    }
    u64* pdpt = table(table(read_cr3())[0]);
    u64* pd = table(pdpt[0]);
    memory_result result{};
    u64* pt = ensure_table(pd, index_of(virtual_address, 21), false, &result);
    if (pt == nullptr) { return result; }
    auto& leaf = pt[index_of(virtual_address, 12)];
    if ((leaf & present) != 0) { return memory_result::already_mapped; }
    leaf = physical | present | writable | no_execute | (1ull << 3) | (1ull << 4);
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
memory_result query_logical_write_in(u64 space, u64 address, bool* result) {
    if (!result || !space || space % page_size || space >= max_managed_phys || address % page_size)
        return memory_result::invalid;
    const u64 e4 = table(space)[index_of(address, 39)];
    if (!(e4 & present) || (e4 & huge)) return memory_result::not_mapped;
    const u64 e3 = table(e4)[index_of(address, 30)];
    if (!(e3 & present) || (e3 & huge)) return memory_result::not_mapped;
    const u64 e2 = table(e3)[index_of(address, 21)];
    if (!(e2 & present) || (e2 & huge)) return memory_result::not_mapped;
    const u64 leaf = table(e2)[index_of(address, 12)];
    if (!(leaf & present)) return memory_result::not_mapped;
    *result = (leaf & logical_writable) != 0;
    return memory_result::none;
}
memory_result query_page(u64 virtual_address, u64* physical, page_permissions* permissions) {
    return query_page_in(read_cr3(), virtual_address, physical, permissions);
}

namespace {
constexpr u64 vm_begin = 0x100000000000ull, vm_end = 0x200000000000ull;
bool valid_vm_location(u64 space, u64 address) {
    return space && !(space % page_size) && space < max_managed_phys &&
           !(address % page_size) && address >= vm_begin && address < vm_end;
}
bool empty_table(const u64* entries) {
    for (u32 i=0;i<512;++i) if (entries[i] != 0) return false;
    return true;
}
u64* vm_leaf(u64 space, u64 address) {
    const u64 e4=table(space)[index_of(address,39)];
    if ((e4 & (present | user | writable)) != (present | user | writable) || (e4 & huge)) return nullptr;
    const u64 e3=table(e4)[index_of(address,30)];
    if ((e3 & (present | user | writable)) != (present | user | writable) || (e3 & huge)) return nullptr;
    const u64 e2=table(e3)[index_of(address,21)];
    if ((e2 & (present | user | writable)) != (present | user | writable) || (e2 & huge)) return nullptr;
    return &table(e2)[index_of(address,12)];
}
bool valid_protection(vm_page_protection value) {
    return value==vm_page_protection::none || value==vm_page_protection::read ||
           value==vm_page_protection::read_write || value==vm_page_protection::read_execute;
}
u64 vm_entry(u64 physical, vm_page_protection protection) {
    if (protection==vm_page_protection::none) return physical | vm_hidden | user | no_execute;
    return physical | present | user |
        (protection==vm_page_protection::read_write ? writable | logical_writable : 0) |
        (protection==vm_page_protection::read_execute ? 0 : no_execute);
}
}
void vm_prune_empty_page_tables_in(u64 space, u64 address) {
    if (!valid_vm_location(space,address)) return;
    u64* pml4=table(space); u64& e4=pml4[index_of(address,39)];
    if ((e4 & (present | user | writable)) != (present | user | writable) || (e4 & huge)) return;
    u64* pdpt=table(e4); u64& e3=pdpt[index_of(address,30)];
    if ((e3 & (present | user | writable)) == (present | user | writable) && !(e3 & huge)) {
        u64* pd=table(e3); u64& e2=pd[index_of(address,21)];
        if ((e2 & (present | user | writable)) == (present | user | writable) &&
            !(e2 & huge) && empty_table(table(e2))) {
            const u64 physical=e2 & address_mask; e2=0; (void)release_page(physical);
        }
        if (empty_table(pd)) {
            const u64 physical=e3 & address_mask; e3=0; (void)release_page(physical);
        }
    }
    if (empty_table(pdpt)) {
        const u64 physical=e4 & address_mask; e4=0; (void)release_page(physical);
    }
}
memory_result vm_scan_page_in(u64 space, u64* cursor, u64 end, bool* found) {
    if (!cursor || !found || !valid_vm_location(space,*cursor) || end<=*cursor ||
        end>0x200000000000ull || (end % page_size)) return memory_result::invalid;
    const u64 address=*cursor;
    *found=false;
    u64* entries=table(space);
    const u32 shifts[]={39,30,21};
    for (u32 i=0;i<3;++i) {
        const u64 entry=entries[index_of(address,shifts[i])];
        if (!(entry & present)) {
            const u64 next=(address | ((u64{1} << shifts[i])-1))+1;
            *cursor=next<end ? next : end;
            return memory_result::none;
        }
        if ((entry & (user | writable)) != (user | writable) || (entry & huge))
            return memory_result::invalid;
        entries=table(entry);
    }
    const u64 leaf=entries[index_of(address,12)];
    if (leaf & (present | vm_hidden)) {
        u64 physical=0; vm_page_protection protection{};
        if (vm_lookup_page_in(space,address,&physical,&protection)!=memory_result::none)
            return memory_result::invalid;
        *found=true;
    }
    *cursor=address+page_size;
    return memory_result::none;
}
memory_result vm_prepare_page_in(u64 space,u64 address) {
    if (!valid_vm_location(space,address)) return memory_result::invalid;
    memory_result result=memory_result::none;
    u64* root=table(space);
    const u64 prior4=root[index_of(address,39)];
    if ((prior4 & present) && (prior4 & (user | writable)) != (user | writable)) return memory_result::invalid;
    u64* pdpt=ensure_table(root,index_of(address,39),true,&result);
    if (!pdpt) return result;
    const u64 prior3=pdpt[index_of(address,30)];
    if ((prior3 & present) && (prior3 & (user | writable)) != (user | writable)) return memory_result::invalid;
    u64* pd=ensure_table(pdpt,index_of(address,30),true,&result);
    if (!pd) { vm_prune_empty_page_tables_in(space,address); return result; }
    const u64 prior2=pd[index_of(address,21)];
    if ((prior2 & present) && (prior2 & (user | writable)) != (user | writable)) return memory_result::invalid;
    u64* pt=ensure_table(pd,index_of(address,21),true,&result);
    if (!pt) { vm_prune_empty_page_tables_in(space,address); return result; }
    return vm_leaf(space,address) ? memory_result::none : memory_result::invalid;
}
memory_result vm_lookup_page_in(u64 space,u64 address,u64* physical,vm_page_protection* protection) {
    if (!valid_vm_location(space,address) || !physical || !protection) return memory_result::invalid;
    const u64* leaf=vm_leaf(space,address);
    if (!leaf || !(*leaf & (present | vm_hidden))) return memory_result::not_mapped;
    const u64 entry=*leaf;
    if ((entry & (present | vm_hidden)) == (present | vm_hidden) ||
        !(entry & user) || !user_page_references(entry & address_mask)) return memory_result::invalid;
    *physical=entry & address_mask;
    *protection=(entry & vm_hidden) ? vm_page_protection::none :
        (entry & writable) ? vm_page_protection::read_write :
        !(entry & no_execute) ? vm_page_protection::read_execute : vm_page_protection::read;
    return memory_result::none;
}
memory_result vm_install_page_in(u64 space,u64 address,u64 physical,vm_page_protection protection) {
    if (!valid_vm_location(space,address) || !valid_protection(protection) || !user_page_references(physical)) return memory_result::invalid;
    u64* leaf=vm_leaf(space,address);
    if (!leaf) return memory_result::not_mapped;
    if (*leaf) return memory_result::already_mapped;
    *leaf=vm_entry(physical,protection); if (read_cr3()==space) invalidate(address);
    return memory_result::none;
}
memory_result vm_protect_page_in(u64 space,u64 address,vm_page_protection protection) {
    if (!valid_protection(protection)) return memory_result::invalid;
    u64 physical=0; vm_page_protection old{};
    const auto result=vm_lookup_page_in(space,address,&physical,&old);
    if (result!=memory_result::none) return result;
    *vm_leaf(space,address)=vm_entry(physical,protection);
    if (read_cr3()==space) invalidate(address);
    return memory_result::none;
}
memory_result vm_remove_page_in(u64 space,u64 address,u64* physical) {
    vm_page_protection old{}; u64 page_physical=0;
    const auto result=vm_lookup_page_in(space,address,&page_physical,&old);
    if (result!=memory_result::none) return result;
    *vm_leaf(space,address)=0; if (read_cr3()==space) invalidate(address);
    if (physical) *physical=page_physical;
    vm_prune_empty_page_tables_in(space,address);
    return memory_result::none;
}

memory_result release_user_pages_batch(u64 space,u64* cursor,u32* released_pages,u32 budget) {
    constexpr u64 end=u64{1}<<47;
    if (!space || space%page_size || space>=max_managed_phys || !cursor || !released_pages ||
        *cursor<0x40000000ull || *cursor>end || *cursor%page_size || !budget)
        return memory_result::invalid;
    while (budget-- && *cursor<end) {
        const u64 address=*cursor;
        u64* root=table(space); u64& e4=root[index_of(address,39)];
        if (!(e4 & present)) { *cursor=(address|((u64{1}<<39)-1))+1; continue; }
        if ((e4 & (user|writable))!=(user|writable) || (e4 & huge)) return memory_result::invalid;
        u64* pdpt=table(e4); u64& e3=pdpt[index_of(address,30)];
        if (!(e3 & present)) { *cursor=(address|((u64{1}<<30)-1))+1; continue; }
        if ((e3 & (user|writable))!=(user|writable) || (e3 & huge)) return memory_result::invalid;
        u64* pd=table(e3); u64& e2=pd[index_of(address,21)];
        if (!(e2 & present)) { *cursor=(address|((u64{1}<<21)-1))+1; continue; }
        if ((e2 & (user|writable))!=(user|writable) || (e2 & huge)) return memory_result::invalid;
        u64* pt=table(e2);u64& leaf=pt[index_of(address,12)];
        if (leaf & (present|vm_hidden)) {
            if ((leaf & (present|vm_hidden))==(present|vm_hidden) || !(leaf & user) ||
                !user_page_references(leaf & address_mask)) return memory_result::invalid;
            const u64 physical=leaf & address_mask;
            leaf=0;if(read_cr3()==space)invalidate(address);
            if(release_user_page(physical)!=memory_result::none)return memory_result::invalid;
            ++*released_pages;
        }
        *cursor+=page_size;
        if (empty_table(pt)) {
            const u64 physical=e2 & address_mask;e2=0;(void)release_page(physical);
            if (empty_table(pd)) {
                const u64 parent=e3 & address_mask;e3=0;(void)release_page(parent);
                if (empty_table(pdpt)) {
                    const u64 grandparent=e4 & address_mask;e4=0;(void)release_page(grandparent);
                }
            }
        }
    }
    return memory_result::none;
}
memory_result copy_user_pages_batch(u64 source, u64 destination, u32 page_limit,
                                    u32* copied_pages, u64* cursor, u32 budget) {
    constexpr u64 end=u64{1}<<47;
    if (!copied_pages || !cursor || !source || !destination || source==destination ||
        source%page_size || destination%page_size || source>=max_managed_phys ||
        destination>=max_managed_phys || *cursor<0x40000000ull || *cursor>end ||
        (*cursor%page_size) || !budget) return memory_result::invalid;
    while (budget-- && *cursor<end) {
        const u64 address=*cursor;
        const u64* entries=table(source);
        const u32 shifts[]={39,30,21};
        u64 parents=present|writable|user;
        bool skip=false;
        for (u32 i=0;i<3;++i) {
            const u64 entry=entries[index_of(address,shifts[i])];
            if (!(entry & present)) {
                const u64 next=(address | ((u64{1}<<shifts[i])-1))+1;
                *cursor=next<end ? next : end; skip=true; break;
            }
            if (entry & huge) return memory_result::invalid;
            parents &= entry;
            entries=table(entry);
        }
        if (skip) continue;
        const u64 leaf=entries[index_of(address,12)];
        if (!(leaf & (present|vm_hidden))) { *cursor+=page_size; continue; }
        const bool hidden=(leaf & vm_hidden)!=0;
        if ((hidden && (leaf & present)) || !(leaf & parents & user) ||
            !user_page_references(leaf & address_mask)) return memory_result::invalid;
        if (*copied_pages>=page_limit) return memory_result::out_of_memory;
        u64 physical=0;
        const auto allocated=allocate_user_page(&physical);
        if (allocated!=memory_result::none) return allocated;
        auto* output=reinterpret_cast<u64*>(physical);
        const auto* input=reinterpret_cast<const u64*>(leaf & address_mask);
        for (u32 word=0;word<page_size/sizeof(u64);++word) output[word]=input[word];
        memory_result mapped;
        if (hidden) {
            mapped=vm_prepare_page_in(destination,address);
            if (mapped==memory_result::none)
                mapped=vm_install_page_in(destination,address,physical,vm_page_protection::none);
            if (mapped!=memory_result::none) vm_prune_empty_page_tables_in(destination,address);
        } else {
            const u64 e4=table(source)[index_of(address,39)];
            const u64 e3=table(e4)[index_of(address,30)];
            const u64 e2=table(e3)[index_of(address,21)];
            const page_permissions perms{(leaf & parents & writable)!=0,
                ((leaf|e2|e3|e4) & no_execute)==0,true};
            mapped=map_page_in(destination,address,physical,perms);
        }
        if (mapped!=memory_result::none) { (void)release_user_page(physical); return mapped; }
        ++*copied_pages; *cursor+=page_size;
    }
    return memory_result::none;
}
memory_result copy_user_pages_in(u64 source, u64 destination, u32 page_limit,
                                 u32* copied_pages) {
    if (copied_pages == nullptr) { return memory_result::invalid; }
    *copied_pages = 0;
    if (source == 0 || destination == 0 || source == destination ||
        source % page_size != 0 || destination % page_size != 0 ||
        source >= max_managed_phys || destination >= max_managed_phys) {
        return memory_result::invalid;
    }
    // Walk the entire canonical lower half. The first PDPT entry is the
    // shared supervisor identity map, never a process-owned mapping.
    const u64* root = table(source);
    for (u32 l4 = 0; l4 < 256; ++l4) {
        const u64 e4 = root[l4];
        if (!(e4 & present)) continue;
        if (e4 & huge) return memory_result::invalid;
        const u64* pdpt = table(e4);
        for (u32 l3 = 0; l3 < 512; ++l3) {
            if (l4 == 0 && l3 == 0) continue;
            const u64 e3 = pdpt[l3];
            if (!(e3 & present)) continue;
            if (e3 & huge) return memory_result::invalid;
            const u64* pd = table(e3);
            for (u32 l2 = 0; l2 < 512; ++l2) {
                const u64 e2 = pd[l2];
                if (!(e2 & present)) continue;
                if (e2 & huge) return memory_result::invalid;
                const u64* pt = table(e2);
                for (u32 l1 = 0; l1 < 512; ++l1) {
                    const u64 leaf = pt[l1];
                    if (!(leaf & present)) continue;
                    const page_permissions perms{
                        (leaf & e2 & e3 & e4 & writable) != 0,
                        ((leaf | e2 | e3 | e4) & no_execute) == 0,
                        (leaf & e2 & e3 & e4 & user) != 0};
                    const u64 source_physical = leaf & address_mask;
                    if (!perms.user || user_page_references(source_physical) == 0)
                        return memory_result::invalid;
                    if (*copied_pages >= page_limit) return memory_result::out_of_memory;
                    u64 physical = 0;
                    const auto allocated = allocate_user_page(&physical);
                    if (allocated != memory_result::none) return allocated;
                    auto* output = reinterpret_cast<u64*>(physical);
                    const auto* input = reinterpret_cast<const u64*>(source_physical);
                    for (u32 word = 0; word < page_size / sizeof(u64); ++word) output[word] = input[word];
                    const u64 address = (u64{l4} << 39) | (u64{l3} << 30) |
                                        (u64{l2} << 21) | (u64{l1} << 12);
                    const auto mapped = map_page_in(destination, address, physical, perms);
                    if (mapped != memory_result::none) {
                        (void)release_user_page(physical); return mapped;
                    }
                    ++*copied_pages;
                }
            }
        }
    }
    return memory_result::none;
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
    for (u32 l4 = 0; l4 < 256; ++l4) {
        const u64 e4 = pml4[l4];
        if (!(e4 & present) || (e4 & huge)) continue;
        u64* pdpt = table(e4);
        for (u32 l3 = 0; l3 < 512; ++l3) {
            if (l4 == 0 && l3 == 0) continue; // shared kernel map
            const u64 e3 = pdpt[l3];
            if (!(e3 & present) || (e3 & huge)) continue;
            u64* pd = table(e3);
            for (u32 l2 = 0; l2 < 512; ++l2) {
                const u64 e2 = pd[l2];
                if (!(e2 & present) || (e2 & huge)) continue;
                u64* pt = table(e2);
                for (u32 l1 = 0; l1 < 512; ++l1) {
                    if (pt[l1] & (present | vm_hidden)) {
                        const u64 physical = pt[l1] & address_mask;
                        const bool last_reference = user_page_references(physical) == 1;
                        if (release_user_page(physical) == memory_result::none && last_reference) ++freed;
                    }
                }
                if (release_page(e2 & address_mask) == memory_result::none) ++freed;
            }
            if (release_page(e3 & address_mask) == memory_result::none) ++freed;
        }
        if (release_page(e4 & address_mask) == memory_result::none) ++freed;
    }
    if (release_page(address_space) == memory_result::none) ++freed;
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
