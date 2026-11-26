#include "ff.h"
#include "diskio.h"
#include <xos/sdk.hpp>

#if XOS_FILES_PRIVATE_STORAGE_PROBE
#include "files_private_storage.hpp"
#endif
#if XOS_FILES_PRIVATE_CLIENT_PROBE
#include "files_private_broker.hpp"
#endif

using xos::u64;
using xos::i64;
static DSTATUS g_status = STA_NOINIT;
static u64 g_sectors;

#if XOS_FILES_PRIVATE_STORAGE_PROBE
namespace xos::user::files_private_storage {
namespace {
region private_region;
}

#if XOS_FILES_PRIVATE_CLIENT_PROBE
slot_io private_slot_io() {
    return {&private_region,
            [](void* context, u32 slot, u8 (&bytes)[slot_bytes]) {
                return static_cast<region*>(context)->read_slot(slot, bytes);
            },
            [](void* context, u32 slot, const u8 (&bytes)[slot_bytes]) {
                return static_cast<region*>(context)->write_slot(slot, bytes);
            }};
}
#else
namespace {
u8 test_byte(u32 slot, u32 index) {
    return static_cast<u8>(0x47 + 29 * slot + 13 * index + index / sector_bytes);
}

bool matches_test_slot(u32 slot, const u8 (&data)[slot_bytes], bool& blank) {
    blank = true;
    bool valid = true;
    for (u32 index = 0; index < slot_bytes; ++index) {
        blank = blank && data[index] == 0;
        valid = valid && data[index] == test_byte(slot, index);
    }
    return valid || blank;
}
}

bool verify_test_slots() {
    u8 data[slot_bytes]{};
    bool blank[slot_count]{};
    for (u32 slot = 0; slot < slot_count; ++slot) {
        if (!private_region.read_slot(slot, data) || !matches_test_slot(slot, data, blank[slot])) {
            return false;
        }
    }
    if (blank[0] && !blank[1]) {
        return false;
    }
    if (!blank[1]) {
        return true;
    }
    const u32 slot = blank[0] ? 0 : 1;
    for (u32 index = 0; index < slot_bytes; ++index) {
        data[index] = test_byte(slot, index);
    }
    bool still_blank = false;
    return private_region.write_slot(slot, data) && private_region.read_slot(slot, data) &&
        matches_test_slot(slot, data, still_blank) && !still_blank;
}
#endif
}
#endif

extern "C" DSTATUS disk_status(BYTE pdrv) {
    if (pdrv != 0) { return STA_NOINIT | STA_NODISK; }
    return g_status;
}

extern "C" DSTATUS disk_initialize(BYTE pdrv) {
    if (pdrv != 0) { return STA_NOINIT | STA_NODISK; }
    u64 sectors = 0;
    const xos::i64 result = xos::sdk::syscall(xos::sys_block_info,
                                              reinterpret_cast<xos::u64>(&sectors));
    if (result != 0 || sectors == 0) {
        g_status = STA_NOINIT | STA_NODISK;
        g_sectors = 0;
        return g_status;
    }
#if XOS_FILES_PRIVATE_STORAGE_PROBE
    auto& region = xos::user::files_private_storage::private_region;
    if (!region.open(sectors)) {
        g_status = STA_NOINIT;
        g_sectors = 0;
        return g_status;
    }
    sectors = region.public_sectors();
#endif
    g_sectors = sectors;
    g_status = 0;
    return g_status;
}

extern "C" DRESULT disk_read(BYTE pdrv, BYTE* buffer, LBA_t sector, UINT count) {
    if (pdrv != 0 || buffer == nullptr || count == 0 ||
        static_cast<u64>(sector) + count > g_sectors) {
        return RES_PARERR;
    }
    u64 offset = 0;
    while (offset < count) {
        const UINT remaining = static_cast<UINT>(count - offset);
        const UINT chunk = remaining > 8 ? 8 : remaining;
        const xos::i64 result = xos::sdk::syscall(
            xos::sys_block_read, static_cast<xos::u64>(sector) + offset,
            reinterpret_cast<xos::u64>(buffer + offset * 512), chunk);
        if (result != 0) {
            return result == xos::block_error_no_device ? RES_NOTRDY : RES_ERROR;
        }
        offset += chunk;
    }
    return RES_OK;
}

extern "C" DRESULT disk_write(BYTE pdrv, const BYTE* buffer, LBA_t sector, UINT count) {
    if (pdrv != 0 || buffer == nullptr || count == 0 ||
        static_cast<u64>(sector) + count > g_sectors) {
        return RES_PARERR;
    }
    u64 offset = 0;
    while (offset < count) {
        const UINT remaining = static_cast<UINT>(count - offset);
        const UINT chunk = remaining > 8 ? 8 : remaining;
        const xos::i64 result = xos::sdk::syscall(
            xos::sys_block_write, static_cast<xos::u64>(sector) + offset,
            reinterpret_cast<xos::u64>(buffer + offset * 512), chunk);
        if (result != 0) {
            return result == xos::block_error_no_device ? RES_NOTRDY : RES_ERROR;
        }
        offset += chunk;
    }
    return RES_OK;
}

extern "C" DRESULT disk_ioctl(BYTE pdrv, BYTE command, void* buffer) {
    if (pdrv != 0) { return RES_PARERR; }
    switch (command) {
    case CTRL_SYNC: {
        const xos::i64 result = xos::sdk::syscall(xos::sys_block_sync);
        return result == 0 ? RES_OK : RES_ERROR;
    }
    case GET_SECTOR_COUNT:
        if (buffer == nullptr) { return RES_PARERR; }
        // FF_LBA64=0 makes LBA_t 32-bit; report the addressable maximum
        // rather than silently wrapping a larger device's sector count.
        *static_cast<LBA_t*>(buffer) = g_sectors > 0xffffffffu
            ? 0xffffffffu : static_cast<LBA_t>(g_sectors);
        return RES_OK;
    case GET_SECTOR_SIZE:
        if (buffer == nullptr) { return RES_PARERR; }
        *static_cast<WORD*>(buffer) = 512;
        return RES_OK;
    case GET_BLOCK_SIZE:
        if (buffer == nullptr) { return RES_PARERR; }
        *static_cast<DWORD*>(buffer) = 1;
        return RES_OK;
    default:
        return RES_PARERR;
    }
}
