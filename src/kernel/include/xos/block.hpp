#pragma once
#include <xos/types.hpp>

namespace xos::block {
enum class result : u8 { none, no_device, invalid, io, timeout };
inline constexpr u32 sector_size = 512;
inline constexpr u32 max_transfer_sectors = 8;

bool init();
bool present();
u64 sector_count();
result read(u64 sector, void* buffer, u32 count);
result write(u64 sector, const void* buffer, u32 count);
result sync();
}
