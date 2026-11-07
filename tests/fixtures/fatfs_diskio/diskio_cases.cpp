// SPDX-License-Identifier: Apache-2.0
// Host regression for the FatFs diskio 32-bit sector arithmetic guards.
#include <cstdio>
#include <cstring>
#include "ff.h"
#include "diskio.h"
#include <xos/sdk.hpp>

namespace {
xos::u64 total_sectors = 100;
xos::u64 last_sector;
unsigned calls;
int failures;

void require(bool value, const char* stage) {
    if (value) { return; }
    std::fprintf(stderr, "FAIL %s sector=%llu calls=%u\n", stage,
                 static_cast<unsigned long long>(last_sector), calls);
    ++failures;
}
}

namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    if (number == xos::sys_block_info) {
        *reinterpret_cast<u64*>(first) = total_sectors;
        return 0;
    }
    if (number == xos::sys_block_read || number == xos::sys_block_write) {
        last_sector = first;
        ++calls;
        (void)second;
        // The kernel also rejects out-of-range requests; returning an error
        // here makes a missed local check visible as RES_ERROR rather than a
        // silently accepted access.
        return first + third <= total_sectors ? 0 : -1;
    }
    return 0;
}
}

int main() {
    BYTE buffer[32 * 512]{};
    require(disk_initialize(0) == 0, "initialize");
    require(total_sectors == 100, "sector count fixture");

    calls = 0;
    require(disk_read(0, buffer, 0xfffffffeu, 4) == RES_PARERR, "read wraparound");
    require(disk_read(0, buffer, 99, 4) == RES_PARERR, "read past end");
    require(disk_read(0, buffer, 96, 4) == RES_OK && calls == 1 && last_sector == 96,
            "read in range");

    calls = 0;
    require(disk_write(0, buffer, 0xfffffffeu, 4) == RES_PARERR, "write wraparound");
    require(disk_write(0, buffer, 99, 4) == RES_PARERR, "write past end");
    require(disk_write(0, buffer, 96, 4) == RES_OK && calls == 1 && last_sector == 96,
            "write in range");

    // A device larger than 2^32 sectors must be clamped in GET_SECTOR_COUNT
    // while the read path keeps a 64-bit absolute sector.
    total_sectors = 0x200000000ull;
    require(disk_initialize(0) == 0, "large initialize");
    LBA_t reported = 0;
    require(disk_ioctl(0, GET_SECTOR_COUNT, &reported) == RES_OK &&
            reported == 0xffffffffu, "sector count clamp");
    calls = 0;
    require(disk_read(0, buffer, 0xfffffff0u, 32) == RES_OK,
            "large device read");
    require(calls == 4 && last_sector == 0x100000008ull,
            "64-bit sector arithmetic");

    if (failures != 0) { return 1; }
    std::printf("FATFS_DISKIO_CASES_PASSED=10\n");
    return 0;
}
