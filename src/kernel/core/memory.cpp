#include <xos/memory.hpp>

namespace xos {
namespace {
constexpr u32 max_pages = static_cast<u32>(max_managed_phys / page_size);
constexpr u32 bitmap_words = max_pages / 64;

// used_bitmap covers reserved and allocated pages; allocated_bitmap only owns
// pages handed out at least once, so a double free cannot release firmware RAM.
u64 used_bitmap[bitmap_words];
u64 allocated_bitmap[bitmap_words];
u32 managed_pages;
u32 free_page_count;
u32 allocated_page_count;
u64 usable_bytes;
u64 managed_high;
u64 first_allocatable;

bool bit_test(const u64* map, u32 index) {
    return (map[index / 64] & (u64{1} << (index % 64))) != 0;
}
void bit_set(u64* map, u32 index) {
    map[index / 64] |= u64{1} << (index % 64);
}
void bit_clear(u64* map, u32 index) {
    map[index / 64] &= ~(u64{1} << (index % 64));
}
u64 align_up(u64 value) {
    return (value + page_size - 1) & ~(page_size - 1);
}
}

void memory_init(const boot_info& info, const memory_region* regions) {
    for (u32 i = 0; i < bitmap_words; ++i) {
        used_bitmap[i] = ~u64{0};
        allocated_bitmap[i] = 0;
    }
    managed_pages = 0;
    free_page_count = 0;
    allocated_page_count = 0;
    usable_bytes = 0;
    managed_high = 0;
    first_allocatable = align_up(info.reserved_low_end);

    u64 highest_usable = 0;
    for (u32 i = 0; i < info.region_count; ++i) {
        const memory_region& region = regions[i];
        if (region.kind != memory_kind::usable) { continue; }
        usable_bytes += region.length;
        const u64 end = region.base + region.length;
        if (end > highest_usable) { highest_usable = end; }
    }
    if (highest_usable > max_managed_phys) { highest_usable = max_managed_phys; }
    managed_pages = static_cast<u32>(highest_usable / page_size);
    managed_high = static_cast<u64>(managed_pages) * page_size;

    // Pages below the loader-reserved low window never become allocatable.
    for (u32 i = 0; i < info.region_count; ++i) {
        const memory_region& region = regions[i];
        if (region.kind != memory_kind::usable) { continue; }
        u64 end = region.base + region.length;
        if (end > managed_high) { end = managed_high; }
        u64 start = region.base;
        if (start < first_allocatable) { start = first_allocatable; }
        start = align_up(start);
        if (start >= end) { continue; }
        u32 last = static_cast<u32>((end + page_size - 1) / page_size);
        if (last > managed_pages) { last = managed_pages; }
        for (u32 page = static_cast<u32>(start / page_size); page < last; ++page) {
            bit_clear(used_bitmap, page);
        }
    }

    // The image, BSS, page tables, boot-info page, and startup stacks stay out
    // of the allocator even if firmware called the containing range usable.
    const u64 kernel_first = info.kernel_start & ~(page_size - 1);
    const u64 kernel_last = align_up(info.kernel_end);
    for (u64 address = kernel_first; address < kernel_last; address += page_size) {
        const u32 page = static_cast<u32>(address / page_size);
        if (page < managed_pages) { bit_set(used_bitmap, page); }
    }

    for (u32 page = 0; page < managed_pages; ++page) {
        if (!bit_test(used_bitmap, page)) { ++free_page_count; }
    }
}

memory_stats memory_status() {
    memory_stats stats{};
    stats.usable_bytes = usable_bytes;
    stats.managed_bytes = managed_high;
    stats.low_address = first_allocatable;
    stats.high_address = managed_high;
    stats.total_pages = managed_pages;
    stats.free_pages = free_page_count;
    stats.allocated_pages = allocated_page_count;
    return stats;
}

memory_result allocate_page(u64* physical) {
    if (physical == nullptr) { return memory_result::invalid; }
    const u32 first = static_cast<u32>(first_allocatable / page_size);
    for (u32 page = first; page < managed_pages; ++page) {
        if (bit_test(used_bitmap, page) || bit_test(allocated_bitmap, page)) { continue; }
        bit_set(used_bitmap, page);
        bit_set(allocated_bitmap, page);
        --free_page_count;
        ++allocated_page_count;
        const u64 address = static_cast<u64>(page) * page_size;
        auto* words = reinterpret_cast<volatile u64*>(address);
        for (u32 i = 0; i < static_cast<u32>(page_size / sizeof(u64)); ++i) {
            words[i] = 0;
        }
        *physical = address;
        return memory_result::none;
    }
    return memory_result::out_of_memory;
}

memory_result release_page(u64 physical) {
    if (physical % page_size != 0 || physical < first_allocatable || physical >= managed_high) {
        return memory_result::invalid;
    }
    const u32 page = static_cast<u32>(physical / page_size);
    if (!bit_test(allocated_bitmap, page)) { return memory_result::invalid; }
    bit_clear(allocated_bitmap, page);
    bit_clear(used_bitmap, page);
    ++free_page_count;
    --allocated_page_count;
    return memory_result::none;
}

const char* memory_result_name(memory_result result) {
    switch (result) {
    case memory_result::none: return "ok";
    case memory_result::invalid: return "invalid";
    case memory_result::out_of_memory: return "out_of_memory";
    case memory_result::already_mapped: return "already_mapped";
    case memory_result::not_mapped: return "not_mapped";
    }
    return "unknown";
}
}
