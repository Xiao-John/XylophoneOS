#include <xos/boot_info.hpp>
using namespace xos;

#define CHECK(condition) do { if (!(condition)) return __LINE__; } while (false)

int main() {
    boot_info info{boot_magic, boot_version, 64, 2, 24, 0x100000, 0x100000,
                   0x108000, firmware_kind::bios, 1, 0};
    memory_region regions[] = {{0, 0xa0000, memory_kind::usable, 1},
                               {0x100000, 0x3e00000, memory_kind::usable, 1}};
    CHECK(validate_boot_info(info, regions) == boot_error::none);
    info.version=boot_display_version;info.size=boot_info_display_size;
    CHECK(validate_boot_info(info,regions)==boot_error::none);
    info.size=64;
    CHECK(validate_boot_info(info,regions)==boot_error::invalid_header);
    info.version=boot_version;info.size=boot_info_display_size;
    CHECK(validate_boot_info(info,regions)==boot_error::invalid_header);
    info.size=64;
    info.firmware = firmware_kind::uefi; // same normalized contract, no UEFI loader implied
    CHECK(validate_boot_info(info, regions) == boot_error::none);
    info.magic = 0;
    CHECK(validate_boot_info(info, regions) == boot_error::invalid_header);
    info.magic = boot_magic;
    info.version = 99;
    CHECK(validate_boot_info(info, regions) == boot_error::invalid_header);
    info.version = boot_version;
    info.flags = 0;
    CHECK(validate_boot_info(info, regions) == boot_error::invalid_header);
    info.flags = 1;
    CHECK(validate_boot_info(info, nullptr) == boot_error::invalid_map);
    info.region_count = 65;
    CHECK(validate_boot_info(info, regions) == boot_error::invalid_map);
    info.region_count = 2;
    regions[1].base = ~u64{0} - 1;
    CHECK(validate_boot_info(info, regions) == boot_error::invalid_map);
    regions[1].base = 0x80000;
    CHECK(validate_boot_info(info, regions) == boot_error::invalid_map);
    regions[1].base = 0x100000;
    regions[1].kind = memory_kind::reserved;
    CHECK(validate_boot_info(info, regions) == boot_error::kernel_not_usable);
    regions[1].kind = memory_kind::usable;
    regions[1].length = 4096;
    CHECK(validate_boot_info(info, regions) == boot_error::kernel_not_usable);
    regions[1].length = 0;
    CHECK(validate_boot_info(info, regions) == boot_error::invalid_map);
    return 0;
}
