// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/types.hpp>
namespace xos::pci {
struct function {u8 bus,slot,number;};
struct bar {u64 address,size;bool memory;};
u32 read32(function f,u16 offset);
void write32(function f,u16 offset,u32 value);
u16 read16(function f,u16 offset);
void write16(function f,u16 offset,u16 value);
bool find(u16 vendor,u16 device,function& result);
bool memory_bar(function f,u8 index,bar& result);
// Kernel-only, bounded UC mapping of validated BAR subranges; no user mapping.
void* map_bar_range(const bar& range,u32 offset,u32 length);
}
