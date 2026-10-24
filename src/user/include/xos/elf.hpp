// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#pragma once
#include <xos/abi_types.hpp>
#include <xos/process_abi.hpp>

namespace xos::elf {
struct segment { u64 offset, address, file_bytes, memory_bytes; u32 permissions; };
struct tls_template { bool present; u64 offset, address, file_bytes, memory_bytes, alignment; };
struct load_plan { u64 entry; u32 count; u32 pages; segment segments[8]; tls_template tls; };
enum class error { none, header, target, unsupported, bounds, alignment, permissions,
                   overlap, entry, too_large, io };
using read_exact_fn = bool (*)(void* context, u64 offset, u8* destination, u32 length);
error inspect_reader(read_exact_fn read_exact, void* context, u64 size, u16 machine,
                     load_plan& result);
error inspect(const u8* bytes, u64 size, u16 machine, load_plan& result);
const char* error_name(error value);
u32 self_check(u16 machine);
}
