// SPDX-License-Identifier: Apache-2.0
#include "image_mapping.hpp"
#include "../../../ports/glibc/sysdeps/xos/xos_image_mapping.h"
#include <xos/vm_abi.hpp>

namespace xos::glibc_d1 {
static_assert(mapped_image_max_loads == XOS_IMAGE_MAX_LOADS);
static_assert(process_max_pages == XOS_IMAGE_MAX_PAGES);
static_assert(vm_page_size == XOS_VM_PAGE && vm_arena_begin == XOS_VM_BEGIN && vm_arena_end == XOS_VM_END);
static_assert(static_cast<u32>(vm_operation::reserve) == XOS_VM_RESERVE);
static_assert(static_cast<u32>(vm_operation::commit) == XOS_VM_COMMIT);
static_assert(static_cast<u32>(vm_operation::protect) == XOS_VM_PROTECT);
static_assert(static_cast<u32>(vm_operation::decommit) == XOS_VM_DECOMMIT);
static_assert(vm_error_resources == XOS_VM_RESOURCES);
static_assert(static_cast<u32>(vm_operation::unmap) == XOS_VM_UNMAP);
static_assert(vm_exact_nonreplace == XOS_VM_EXACT);
static_assert(map_read == 4 && map_write == 2 && map_execute == 1);

image_map_result map_verified_image(const mapped_image& layout, u64 file_size,
                                    elf::read_exact_fn read, void* context,
                                    image_map_budget budget, image_allocation& allocation) {
    if (layout.loads == nullptr || layout.load_count > mapped_image_max_loads) {
        return {image_map_error::layout, 0, 0};
    }
    xos_image_segment loads[mapped_image_max_loads];
    for (u32 i = 0; i < layout.load_count; ++i) {
        const auto& p = layout.loads[i];
        loads[i] = {p.offset, p.address, p.file_bytes, p.memory_bytes, p.permissions};
    }
    const xos_image_mapping mapping{layout.bias, layout.entry, file_size, budget.reservation_bytes,
                                    budget.committed_bytes, loads, layout.load_count};
    xos_image_allocation range{allocation.start, allocation.bytes};
    const auto result = xos_image_map(&mapping, read, context, &range);
    if (result.error == xos_image_map_ok) { allocation = {range.start, range.bytes}; }
    return {static_cast<image_map_error>(result.error), result.vm_error, result.rollback_error};
}

i64 release_image(image_allocation& allocation) {
    xos_image_allocation range{allocation.start, allocation.bytes};
    const auto result = xos_image_release(&range);
    if (result == 0) { allocation = {}; }
    return result;
}
}
