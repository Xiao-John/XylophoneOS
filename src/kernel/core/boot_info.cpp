#include <xos/boot_info.hpp>
#include <xos/memory.hpp>

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
    if (!kernel_covered) { return boot_error::kernel_not_usable; }
    if (info.reserved != 0) {
        if (info.reserved < 4096 || info.reserved_low_end < sizeof(boot_payload_descriptor) ||
            info.reserved > info.reserved_low_end - sizeof(boot_payload_descriptor)) {
            return boot_error::invalid_header;
        }
        const auto& payload = *reinterpret_cast<const boot_payload_descriptor*>(info.reserved);
        if (payload.magic != boot_payload_magic || payload.size == 0 ||
            payload.size > boot_payload_max_bytes || payload.address < info.kernel_end ||
            payload.address > max_managed_phys - payload.size) { return boot_error::invalid_header; }
        bool payload_covered = false;
        for (u32 i = 0; i < info.region_count; ++i) {
            if (regions[i].kind == memory_kind::usable && regions[i].base <= payload.address &&
                regions[i].base + regions[i].length >= payload.address + payload.size) {
                payload_covered = true;
            }
        }
        if (!payload_covered) { return boot_error::invalid_header; }
    }
    return boot_error::none;
}
}
