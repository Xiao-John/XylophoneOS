#include <xos/boot_info.hpp>

namespace xos {
boot_error validate_boot_info(const boot_info& info, const memory_region* regions) {
    if (info.magic != boot_magic || info.version != boot_version ||
        info.size != sizeof(boot_info) || info.region_stride != sizeof(memory_region) ||
        info.flags != 1 ||
        (info.firmware != firmware_kind::bios && info.firmware != firmware_kind::uefi) ||
        info.kernel_start < info.reserved_low_end || info.kernel_end <= info.kernel_start) {
        return boot_error::invalid_header;
    }
    if (regions == nullptr || info.region_count == 0 || info.region_count > max_memory_regions) {
        return boot_error::invalid_map;
    }
    bool kernel_covered = false;
    for (u32 i = 0; i < info.region_count; ++i) {
        const auto& region = regions[i];
        if (region.length == 0 || region.base > ~u64{0} - region.length ||
            region.attributes != 1 || static_cast<u32>(region.kind) < 1 ||
            static_cast<u32>(region.kind) > 5) {
            return boot_error::invalid_map;
        }
        const u64 end = region.base + region.length;
        for (u32 j = 0; j < i; ++j) {
            if (region.base < regions[j].base + regions[j].length && regions[j].base < end) {
                return boot_error::invalid_map;
            }
        }
        if (region.kind == memory_kind::usable && region.base <= info.kernel_start &&
            end >= info.kernel_end) {
            kernel_covered = true;
        }
    }
    return kernel_covered ? boot_error::none : boot_error::kernel_not_usable;
}
}
