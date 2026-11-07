#include "ff.h"
#include "diskio.h"
#include <xos/sdk.hpp>

using xos::u64;
using xos::i64;
static DSTATUS g_status = STA_NOINIT;
static u64 g_sectors;

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
