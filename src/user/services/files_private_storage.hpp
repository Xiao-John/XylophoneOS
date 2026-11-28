// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/sdk.hpp>

namespace xos::user::files_private_storage {

// Internal, opt-in fixed-region layout. A 9-sector slot accommodates the
// maximum 4432-byte Pumpkin snapshot with spare bytes for future framing.
inline constexpr u32 sector_bytes = 512;
#if XOS_PUMPKIN_PROVISIONING_STORE
inline constexpr u32 region_version = 2;
inline constexpr u32 slot_sectors = 32;
#else
inline constexpr u32 region_version = 1;
inline constexpr u32 slot_sectors = 9;
#endif
inline constexpr u32 slot_bytes = slot_sectors * sector_bytes;
inline constexpr u32 slot_count = 2;
inline constexpr u32 tail_sectors = 1 + slot_count * slot_sectors;
inline constexpr u64 min_public_sectors = (512ull << 20) / sector_bytes;
inline constexpr u64 max_ata_sectors = 0x0fffffffull;

class region {
public:
    bool open(u64 device_sectors) {
        public_sectors_ = 0;
        if (device_sectors < min_public_sectors + tail_sectors || device_sectors > max_ata_sectors) {
            return false;
        }
        const u64 prefix = device_sectors - tail_sectors;
        u8 sector[sector_bytes]{};
        if (!read_sectors(prefix, sector, 1) || !valid_descriptor(sector, prefix) ||
            !read_sectors(0, sector, 1) || !valid_boot_sector(sector, prefix) ||
            !read_sectors(6, sector, 1) || !valid_boot_sector(sector, prefix)) {
            return false;
        }
        public_sectors_ = prefix;
        return true;
    }

    u64 public_sectors() const { return public_sectors_; }

    bool read_slot(u32 slot, u8 (&data)[slot_bytes]) const {
        if (public_sectors_ == 0 || slot >= slot_count) {
            return false;
        }
        const u64 sector = slot_start(slot);
        for (u32 offset = 0; offset < slot_sectors;) {
            const u32 count = slot_sectors - offset < 8 ? slot_sectors - offset : 8;
            if (!read_sectors(sector + offset, data + offset * sector_bytes, count)) { return false; }
            offset += count;
        }
        return true;
    }

    bool write_slot(u32 slot, const u8 (&data)[slot_bytes]) const {
        if (public_sectors_ == 0 || slot >= slot_count) {
            return false;
        }
        const u64 sector = slot_start(slot);
        for (u32 offset = 0; offset < slot_sectors;) {
            const u32 count = slot_sectors - offset < 8 ? slot_sectors - offset : 8;
            if (!write_sectors(sector + offset, data + offset * sector_bytes, count)) { return false; }
            offset += count;
        }
        return sdk::syscall(sys_block_sync) == 0;
    }

private:
    static u64 read_le(const u8* bytes, u32 length) {
        u64 value = 0;
        for (u32 index = 0; index < length; ++index) {
            value |= static_cast<u64>(bytes[index]) << (index * 8);
        }
        return value;
    }

    static bool valid_descriptor(const u8 (&data)[sector_bytes], u64 prefix) {
        constexpr char magic[] = "XOSPRIV1";
        for (u32 index = 0; index < sizeof(magic) - 1; ++index) {
            if (data[index] != magic[index]) {
                return false;
            }
        }
        if (read_le(data + 8, 4) != region_version || read_le(data + 12, 4) != slot_sectors ||
            read_le(data + 16, 8) != prefix) {
            return false;
        }
        for (u32 index = 24; index < sector_bytes; ++index) {
            if (data[index] != 0) {
                return false;
            }
        }
        return true;
    }

    static bool valid_boot_sector(const u8 (&data)[sector_bytes], u64 prefix) {
        // The opt-in formatter uses an unpartitioned FAT32 volume with a
        // backup boot sector at LBA 6. Public disk I/O is capped separately.
        constexpr char kind[] = "FAT32   ";
        for (u32 index = 0; index < sizeof(kind) - 1; ++index) {
            if (data[82 + index] != kind[index]) {
                return false;
            }
        }
        return data[0] == 0xeb && data[510] == 0x55 && data[511] == 0xaa &&
            read_le(data + 11, 2) == sector_bytes && read_le(data + 17, 2) == 0 &&
            read_le(data + 19, 2) == 0 && read_le(data + 22, 2) == 0 &&
            read_le(data + 28, 4) == 0 && read_le(data + 32, 4) == prefix &&
            read_le(data + 50, 2) == 6;
    }

    static bool read_sectors(u64 start, u8* output, u32 count) {
        return sdk::syscall(sys_block_read, start, reinterpret_cast<u64>(output), count) == 0;
    }

    static bool write_sectors(u64 start, const u8* input, u32 count) {
        return sdk::syscall(sys_block_write, start, reinterpret_cast<u64>(input), count) == 0;
    }

    u64 slot_start(u32 slot) const {
        return public_sectors_ + 1 + slot * slot_sectors;
    }

    u64 public_sectors_ = 0;
};

// Added only to a disposable test image. There is no public request handler.
bool verify_test_slots();

}
