#pragma once
#include <xos/abi_types.hpp>
#include <xos/process_abi.hpp>

namespace xos::elf {
struct segment { u64 offset, address, file_bytes, memory_bytes; u32 permissions; };
struct load_plan { u64 entry; u32 count; u32 pages; segment segments[8]; };
enum class error { none, header, target, unsupported, bounds, alignment, permissions,
                   overlap, entry, too_large };
error inspect(const u8* bytes, u64 size, u16 machine, load_plan& result);
const char* error_name(error value);
u32 self_check(u16 machine);
}
