// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/memory.hpp>

namespace xos {
// A syscall stages every COW destination before consuming input or publishing
// output. Records live in the thread, outside its 4 KiB kernel stack.
struct user_copyout {
    static constexpr u32 capacity = 64;
    u64 space = 0;
    u32 count = 0;
    memory_result failure = memory_result::none;
    user_write_page pages[capacity]{};

    void rollback() {
        for (u32 i = 0; i < count; ++i) {
            if (pages[i].replacement != 0) {
                (void)release_user_page(pages[i].replacement);
            }
        }
        count = 0;
        space = 0;
    }

    void reset() { rollback(); failure = memory_result::none; }

    memory_result reject(memory_result result) {
        rollback();
        failure = result;
        return result;
    }

    // first/last are already checked, inclusive page addresses in this owner.
    memory_result prepare(u64 owner, u64 first, u64 last) {
        const u32 previous = count;
        space = owner;
        for (u64 address = first; address <= last; address += page_size) {
            bool staged = false;
            for (u32 i = 0; i < count; ++i) {
                if (pages[i].address == address) { staged = true; break; }
            }
            if (staged) { continue; }
            user_write_page page{};
            const auto result = inspect_user_write_in(owner, address, page);
            if (result != memory_result::none) { return reject(result); }
            if (page.address == 0) { continue; }
            if (count == capacity) { return reject(memory_result::out_of_memory); }
            pages[count++] = page;
        }
        // Check the whole logical range before allocating any replacement.
        for (u32 i = previous; i < count; ++i) {
            const auto result = stage_user_write(pages[i]);
            if (result != memory_result::none) { return reject(result); }
        }
        return memory_result::none;
    }

    memory_result commit() {
        for (u32 i = 0; i < count; ++i) {
            if (!user_write_unchanged_in(space, pages[i])) {
                return reject(memory_result::invalid);
            }
        }
        for (u32 i = 0; i < count; ++i) { publish_user_write_in(space, pages[i]); }
        count = 0;
        space = 0;
        return memory_result::none;
    }
};
}
