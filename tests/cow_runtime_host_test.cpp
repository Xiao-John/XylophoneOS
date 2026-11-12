// SPDX-License-Identifier: Apache-2.0
#include <xos/memory.hpp>
#include "arch/x86_64/cow1_probe.hpp"
#include "core/user_copyout.hpp"
#include <sys/mman.h>
#include <cassert>
#include <cstdlib>
#include <cstdio>

xos::u64 host_active_cr3, host_invalidations;
namespace xos::arch { [[noreturn]] void halt() { std::abort(); } }
namespace {
using namespace xos;
constexpr u64 physical_base = 0x10000000;
constexpr u64 physical_bytes = 32 * 1024 * 1024;
constexpr u64 data_address = 0x100000000000;

u64 make_space() {
    const auto space = arch::create_address_space();
    assert(space != 0);
    return space;
}

u64 add_page(u64 space, u64 address, bool write = true) {
    u64 physical = 0;
    assert(allocate_user_page(&physical) == memory_result::none);
    assert(map_page_in(space, address, physical, {write, false, true}) == memory_result::none);
    *reinterpret_cast<u64*>(physical) = 0x12345678;
    return physical;
}

u64 mapped_page(u64 space, u64 address, bool expected_write) {
    u64 physical = 0;
    page_permissions permissions{};
    assert(query_page_in(space, address, &physical, &permissions) == memory_result::none);
    assert(permissions.user && permissions.writable == expected_write);
    return physical;
}

void snapshot(u64 parent, u64 child, u32 count) {
    u64 cursor = data_address;
    u32 copied = 0;
    while (cursor < (u64{1} << 47))
        assert(arch::cow1_stage_batch(parent, child, 4096, &copied, &cursor, 8, nullptr) == memory_result::none);
    assert(copied == count);
    cursor = data_address;
    while (cursor < (u64{1} << 47))
        assert(arch::cow1_publish_batch(parent, child, &cursor, 8) == memory_result::none);
}

void verify_empty(u32 baseline) {
    assert(user_pages_status().unique_pages == 0 && user_pages_status().references == 0);
    assert(memory_status().allocated_pages == baseline);
}
}

int main() {
    using namespace xos;
    void* mapping = mmap(reinterpret_cast<void*>(physical_base), physical_bytes,
                         PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    assert(mapping == reinterpret_cast<void*>(physical_base));
    boot_info info{};
    info.reserved_low_end = physical_base;
    info.region_count = 1;
    memory_region region{physical_base, physical_bytes, memory_kind::usable, 0};
    memory_init(info, &region);
    u64 bootstrap_pdpt = 0, bootstrap_pd = 0;
    assert(allocate_page(&host_active_cr3) == memory_result::none);
    assert(allocate_page(&bootstrap_pdpt) == memory_result::none);
    assert(allocate_page(&bootstrap_pd) == memory_result::none);
    reinterpret_cast<u64*>(host_active_cr3)[0] = bootstrap_pdpt | 3;
    reinterpret_cast<u64*>(bootstrap_pdpt)[0] = bootstrap_pd | 3;
    const u64 bootstrap = host_active_cr3;
    const u32 baseline = memory_status().allocated_pages;

    // A later allocation failure must not change an earlier destination page.
    {
        const u64 parent = make_space(), child = make_space();
        const u64 first = add_page(parent, data_address);
        const u64 second = add_page(parent, data_address + page_size);
        snapshot(parent, child, 2);
        user_copyout output;
        const u32 before = memory_status().allocated_pages;
        memory_self_test_fail_after(1);
        assert(output.prepare(parent, data_address, data_address + page_size) == memory_result::out_of_memory);
        memory_self_test_fail_after(-1);
        assert(output.count == 0 && memory_status().allocated_pages == before);
        assert(mapped_page(parent, data_address, false) == first);
        assert(mapped_page(parent, data_address + page_size, false) == second);
        assert(user_page_references(first) == 2 && user_page_references(second) == 2);
        output.reset();
        assert(output.prepare(parent, data_address, data_address + page_size) == memory_result::none);
        assert(mapped_page(parent, data_address, false) == first);
        assert(output.prepare(parent, data_address, data_address) == memory_result::none && output.count == 2);
        assert(output.commit() == memory_result::none);
        const u64 private_first = mapped_page(parent, data_address, true);
        assert(private_first != first && *reinterpret_cast<u64*>(private_first) == 0x12345678);
        *reinterpret_cast<u64*>(private_first) = 0x98765432;
        assert(*reinterpret_cast<u64*>(mapped_page(child, data_address, false)) == 0x12345678);
        arch::destroy_address_space(parent);
        assert(arch::cow1_resolve_page(child, data_address) == memory_result::none);
        assert(mapped_page(child, data_address, true) == first && user_page_references(first) == 1);
        arch::destroy_address_space(child);
        verify_empty(baseline);
    }
    std::puts("PASS copyout allocation rollback, atomic publication, duplicate ranges, parent exit and child sole-owner write");

    // Cross-range validation and stale-token rejection roll back every staged copy.
    {
        const u64 parent = make_space(), child = make_space();
        const u64 original = add_page(parent, data_address);
        add_page(parent, data_address + page_size, false);
        snapshot(parent, child, 2);
        user_copyout output;
        const u32 before = memory_status().allocated_pages;
        assert(output.prepare(parent, data_address, data_address) == memory_result::none);
        assert(output.prepare(parent, data_address + page_size, data_address + page_size) == memory_result::invalid);
        assert(output.count == 0 && memory_status().allocated_pages == before);
        assert(mapped_page(parent, data_address, false) == original);
        output.reset();
        assert(output.prepare(parent, data_address, data_address) == memory_result::none);
        assert(vm_protect_page_in(parent, data_address, vm_page_protection::read) == memory_result::none);
        assert(output.commit() == memory_result::invalid && memory_status().allocated_pages == before);
        arch::destroy_address_space(child);
        arch::destroy_address_space(parent);
        verify_empty(baseline);
    }
    std::puts("PASS cross-range permission rollback and unchanged-mapping commit check");

    // Logical permissions survive NONE/READ transitions and COW fork rollback.
    {
        const u64 parent = make_space(), child = make_space();
        const u64 original = add_page(parent, data_address);
        snapshot(parent, child, 1);
        assert(vm_protect_page_in(parent, data_address, vm_page_protection::none) == memory_result::none);
        assert(vm_protect_page_in(parent, data_address, vm_page_protection::read_write) == memory_result::none);
        assert(mapped_page(parent, data_address, false) == original);
        assert(arch::cow1_resolve_page(parent, data_address) == memory_result::none);
        assert(mapped_page(parent, data_address, true) != original);
        arch::destroy_address_space(child);
        arch::destroy_address_space(parent);
        verify_empty(baseline);
        const u64 source = make_space(), aborted = make_space();
        const u64 page = add_page(source, data_address);
        i64 retained = 0;
        assert(arch::cow1_stage_page(source, aborted, data_address, &retained) == memory_result::out_of_memory);
        assert(user_page_references(page) == 1 && mapped_page(source, data_address, true) == page);
        arch::destroy_address_space(aborted);
        arch::destroy_address_space(source);
        verify_empty(baseline);
    }
    std::puts("PASS logical protection restore and fork retain failure cleanup");

    // Intentionally shared writable mappings must remain shared.
    {
        const u64 first_space = make_space(), second_space = make_space();
        const u64 shared = add_page(first_space, data_address);
        assert(retain_user_page(shared) == memory_result::none);
        assert(map_page_in(second_space, data_address, shared, {true, false, true}) == memory_result::none);
        user_copyout output;
        assert(output.prepare(first_space, data_address, data_address) == memory_result::none && output.count == 0);
        assert(output.commit() == memory_result::none);
        assert(mapped_page(first_space, data_address, true) == shared && user_page_references(shared) == 2);
        arch::destroy_address_space(first_space);
        arch::destroy_address_space(second_space);
        verify_empty(baseline);
    }
    std::puts("PASS explicit writable sharing remains shared");
    {
        const u64 parent = make_space(), child = make_space(), grandchild = make_space();
        const u64 original = add_page(parent, data_address);
        snapshot(parent, child, 1);
        snapshot(child, grandchild, 1);
        assert(user_page_references(original) == 3);
        assert(arch::cow1_resolve_page(parent, data_address) == memory_result::none);
        *reinterpret_cast<u64*>(mapped_page(parent, data_address, true)) = 1;
        assert(arch::cow1_resolve_page(child, data_address) == memory_result::none);
        *reinterpret_cast<u64*>(mapped_page(child, data_address, true)) = 2;
        assert(arch::cow1_resolve_page(grandchild, data_address) == memory_result::none);
        assert(mapped_page(grandchild, data_address, true) == original);
        assert(*reinterpret_cast<u64*>(original) == 0x12345678);
        assert(user_pages_status().unique_pages == 3 && user_pages_status().references == 3);
        arch::destroy_address_space(child);
        arch::destroy_address_space(parent);
        arch::destroy_address_space(grandchild);
        verify_empty(baseline);
    }
    std::puts("PASS three-generation private writes and exact final reference cleanup");
    {
        const u64 parent = make_space(), child = make_space();
        for (u32 i = 0; i <= user_copyout::capacity; ++i) { add_page(parent, data_address + i * page_size); }
        snapshot(parent, child, user_copyout::capacity + 1);
        const u32 before = memory_status().allocated_pages;
        user_copyout output;
        assert(output.prepare(parent, data_address, data_address + 31 * page_size) == memory_result::none);
        assert(output.prepare(parent, data_address + 32 * page_size,
                              data_address + user_copyout::capacity * page_size) == memory_result::out_of_memory);
        assert(output.count == 0 && memory_status().allocated_pages == before);
        arch::destroy_address_space(parent);
        arch::destroy_address_space(child);
        verify_empty(baseline);
    }
    std::puts("PASS bounded copyout metadata exhaustion rolls back earlier output ranges");
    {
        const u64 parent = make_space(), eager = make_space(), cow = make_space();
        add_page(parent, data_address);
        add_page(parent, data_address + page_size, false);
        add_page(parent, data_address + 2 * page_size);
        assert(vm_protect_page_in(parent, data_address + 2 * page_size, vm_page_protection::none) == memory_result::none);
        u32 copied = 0;
        assert(copy_user_pages_in(parent, eager, 4096, &copied) == memory_result::none && copied == 3);
        assert(user_pages_status().unique_pages == 6 && user_pages_status().references == 6);
        snapshot(parent, cow, 3);
        assert(user_pages_status().unique_pages == 6 && user_pages_status().references == 9);
        assert(*reinterpret_cast<u64*>(mapped_page(eager, data_address, true)) ==
               *reinterpret_cast<u64*>(mapped_page(cow, data_address, false)));
        (void)mapped_page(eager, data_address + page_size, false);
        (void)mapped_page(cow, data_address + page_size, false);
        const u64 controls[] = {eager, cow};
        for (u64 space : controls) {
            u64 physical = 0;
            vm_page_protection protection{};
            assert(vm_lookup_page_in(space, data_address + 2 * page_size, &physical, &protection) == memory_result::none);
            assert(protection == vm_page_protection::none && *reinterpret_cast<u64*>(physical) == 0x12345678);
        }
        arch::destroy_address_space(parent);
        arch::destroy_address_space(eager);
        arch::destroy_address_space(cow);
        verify_empty(baseline);
    }
    std::puts("PASS eager/COW real page backend equivalence: RW/R/NONE; eager adds 3 unique data pages, COW adds 0");
    host_active_cr3 = bootstrap;
    assert(munmap(mapping, physical_bytes) == 0);
}
