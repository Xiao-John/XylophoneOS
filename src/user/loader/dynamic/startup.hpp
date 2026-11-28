// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/dynamic_launch.hpp>
#include <xos/dynamic_startup_abi.h>
#include <xos/thread_abi.hpp>

namespace xos::dynamic {
struct startup_image {
    u64 entry, phoff, phaddr;
    u32 phnum, load_count;
    elf::segment loads[elf_load_limit];
};
struct startup_pin { u32 handle, inode; };
struct startup_capsule {
    xos_dynamic_startup_prefix prefix;
    launch_policy policy;
    generation selected;
    startup_image images[generation_max_objects];
    startup_pin pins[generation_max_objects];
};
inline constexpr u32 capsule_pages = (sizeof(startup_capsule) + 4095) / 4096;
inline constexpr u64 capsule_end = XOS_DYNAMIC_STARTUP_ADDRESS + capsule_pages * 4096;
static_assert(capsule_pages <= 16);
static_assert(XOS_DYNAMIC_STARTUP_ADDRESS % 4096 == 0);
static_assert(XOS_DYNAMIC_STARTUP_ADDRESS >= process_user_begin);
static_assert(XOS_DYNAMIC_STARTUP_ADDRESS >= process_tls_end);
static_assert(XOS_DYNAMIC_STARTUP_ADDRESS >= process_heap_end);
static_assert(XOS_DYNAMIC_STARTUP_ADDRESS >= thread_arena_end);
static_assert(capsule_end <= process_stack_guard);
static_assert(capsule_end <= generation_mapping_begin);
static_assert(capsule_end <= startup_heap_base);
static_assert(generation_mapping_end <= startup_heap_base);
bool validate_capsule(const startup_capsule& capsule);
}
