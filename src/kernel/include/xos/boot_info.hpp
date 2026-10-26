#pragma once
#include <xos/types.hpp>

namespace xos {
// Normalized data owned by the loader; valid until the kernel copies it.
// Firmware-specific records and callbacks never cross this boundary.
inline constexpr u64 boot_magic = 0x314f464e49534f58;
inline constexpr u32 boot_version = 1;
inline constexpr u32 max_memory_regions = 64;
enum class firmware_kind : u32 { bios = 1, uefi = 2 };
enum class memory_kind : u32 { usable = 1, reserved = 2, acpi_reclaim = 3,
                              acpi_nvs = 4, bad = 5 };
struct memory_region {
    u64 base;
    u64 length;
    memory_kind kind;
    u32 attributes; // bit 0: enabled; no firmware-specific extension bits
};
struct boot_info {
    u64 magic;
    u32 version;
    u32 size;
    u32 region_count;
    u32 region_stride;
    u64 reserved_low_end;
    u64 kernel_start;
    u64 kernel_end;
    firmware_kind firmware;
    u32 flags; // bit 0: memory map complete; other bits reserved
    u64 reserved; // optional normalized boot_payload_descriptor in reserved low RAM
};
static_assert(sizeof(memory_region) == 24);
static_assert(sizeof(boot_info) == 64);
static_assert(__builtin_offsetof(boot_info, region_count) == 16);
static_assert(__builtin_offsetof(boot_info, kernel_start) == 32);
static_assert(__builtin_offsetof(boot_info, firmware) == 48);
// Boot data has no firmware record or instruction-set dependency.
inline constexpr u64 boot_payload_magic = 0x31444c50534f5858ull; // XXOSPLD1
inline constexpr u64 boot_payload_max_bytes = 32ull * 1024 * 1024;
struct boot_payload_descriptor {
    u64 magic;
    u64 address;
    u64 size;
};
static_assert(sizeof(boot_payload_descriptor) == 24);
inline constexpr u32 boot_display_version = 2;
struct boot_display {
    u32 version, size, width, height, stride, format;
    u64 physical, bytes;
    u32 status, reserved; // 1 ready, 0 absent/unsupported; no firmware structures
};
static_assert(sizeof(boot_display) == 48);
inline constexpr u32 boot_info_display_size = sizeof(boot_info) + sizeof(boot_display);
enum class boot_error { none, invalid_header, invalid_map, kernel_not_usable };
boot_error validate_boot_info(const boot_info& info, const memory_region* regions);
}
