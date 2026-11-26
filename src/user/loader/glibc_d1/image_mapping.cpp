// SPDX-License-Identifier: Apache-2.0
#include "image_mapping.hpp"
#include <xos/vm.hpp>

namespace xos::glibc_d1 {
namespace {
constexpr u64 page_mask = vm_page_size - 1;
constexpr u64 image_bytes_limit = u64{process_max_pages} * vm_page_size;
// Current sys67 commit and protect transaction limit.
constexpr u64 vm_transaction_bytes = 4096 * vm_page_size;

u64 page_begin(u64 address) { return address & ~page_mask; }
u64 page_end(u64 address) { return (address + page_mask) & ~page_mask; }

vm_protection protection(u32 permissions) {
    switch (permissions) {
        case map_read: return vm_protection::read;
        case map_read | map_write: return vm_protection::read_write;
        case map_read | map_execute: return vm_protection::read_execute;
        default: return vm_protection::none;
    }
}

image_map_error plan_range(const mapped_image& layout, u64 file_size, image_map_budget budget,
                           image_allocation& range) {
    if (layout.bias < vm_arena_begin || layout.bias >= vm_arena_end || (layout.bias & page_mask) != 0 ||
        layout.loads == nullptr || layout.load_count == 0 || layout.load_count > mapped_image_max_loads) {
        return image_map_error::layout;
    }
    if (budget.reservation_bytes == 0 || budget.committed_bytes == 0) { return image_map_error::budget; }
    const u64 address_limit = vm_arena_end - layout.bias;
    u64 begin = 0, end = 0, committed = 0;
    bool entry_found = layout.entry == 0;  // A DSO may have no entry.
    for (u32 index = 0; index < layout.load_count; ++index) {
        const auto& load = layout.loads[index];
        if (load.address >= address_limit || load.memory_bytes == 0 ||
            load.memory_bytes > address_limit - load.address || load.file_bytes > load.memory_bytes ||
            load.offset > file_size || load.file_bytes > file_size - load.offset ||
            (load.address & page_mask) != (load.offset & page_mask) ||
            protection(load.permissions) == vm_protection::none) {
            return image_map_error::layout;
        }
        const u64 first = page_begin(load.address);
        if (index == 0) { begin = first; }
        if (index != 0 && first < end) { return image_map_error::layout; }
        end = page_end(load.address + load.memory_bytes);
        committed += end - first;
        if (end - begin > budget.reservation_bytes || end - begin > image_bytes_limit ||
            committed > budget.committed_bytes) { return image_map_error::budget; }
        if ((load.permissions & map_execute) != 0 && layout.entry >= load.address &&
            layout.entry - load.address < load.file_bytes) { entry_found = true; }
    }
    if (!entry_found) { return image_map_error::layout; }
    range = {layout.bias + begin, end - begin};
    return image_map_error::none;
}

i64 change_load(vm_operation operation, const mapped_image& layout, const elf::segment& load,
                vm_protection access) {
    const u64 start = layout.bias + page_begin(load.address);
    const u64 end = layout.bias + page_end(load.address + load.memory_bytes);
    for (u64 address = start; address < end;) {
        const u64 size = end - address < vm_transaction_bytes ? end - address : vm_transaction_bytes;
        const i64 result = sdk::vm_change(operation, address, size, access);
        if (result != 0) { return result; }
        address += size;
    }
    return 0;
}

image_map_result failed(image_map_error error, i64 vm_error, image_allocation& range) {
    return {error, vm_error, release_image(range)};
}
}

image_map_result map_verified_image(const mapped_image& layout, u64 file_size,
                                    elf::read_exact_fn read, void* context,
                                    image_map_budget budget, image_allocation& allocation) {
    if (read == nullptr || allocation.start != 0 || allocation.bytes != 0) {
        return {image_map_error::layout, 0, 0};
    }
    image_allocation range{};
    const image_map_error planned = plan_range(layout, file_size, budget, range);
    if (planned != image_map_error::none) { return {planned, 0, 0}; }
    const i64 reserved = sdk::vm_reserve(range.start, range.bytes, vm_page_size, true);
    if (reserved < 0) { return {image_map_error::reserve, reserved, 0}; }
    if (static_cast<u64>(reserved) != range.start) {
        range.start = static_cast<u64>(reserved);
        return failed(image_map_error::reserve, vm_error_address, range);
    }
    for (u32 index = 0; index < layout.load_count; ++index) {
        const auto& load = layout.loads[index];
        const i64 result = change_load(vm_operation::commit, layout, load, vm_protection::read_write);
        if (result != 0) { return failed(image_map_error::commit, result, range); }
        // Fresh native pages are zeroed. Copy only the linked file bytes.
        if (load.file_bytes != 0 && !read(context, load.offset,
                reinterpret_cast<u8*>(layout.bias + load.address), static_cast<u32>(load.file_bytes))) {
            return failed(image_map_error::read, 0, range);
        }
    }
    for (u32 index = 0; index < layout.load_count; ++index) {
        const auto& load = layout.loads[index];
        const vm_protection access = protection(load.permissions);
        if (access == vm_protection::read_write) { continue; }
        const i64 result = change_load(vm_operation::protect, layout, load, access);
        if (result != 0) { return failed(image_map_error::protect, result, range); }
    }
    allocation = range;
    return {image_map_error::none, 0, 0};
}

i64 release_image(image_allocation& allocation) {
    if (allocation.bytes == 0) { return allocation.start == 0 ? 0 : vm_error_invalid; }
    const i64 result = sdk::vm_change(vm_operation::unmap, allocation.start, allocation.bytes);
    if (result == 0) { allocation = {}; }
    return result;
}
}
