// SPDX-License-Identifier: Apache-2.0
// PC configuration mechanism #1. Boot/debug discovery only; no hotplug/SMP claim.
#include <xos/pci.hpp>
#include <xos/memory.hpp>
#include <xos/device_backend.hpp>
#include <xos/platform.hpp>
#include "arch/x86_64/io.hpp"
namespace xos::pci {
namespace {
u32 address(function f,u16 offset){return 0x80000000u|(u32(f.bus)<<16)|(u32(f.slot)<<11)|(u32(f.number)<<8)|(offset&0xfcu);}
u64 next_mapping=0x32000000ull;
}
u32 read32(function f,u16 offset){if(offset>252)return ~u32{0};arch::out_dword(0xcf8,address(f,offset));return arch::in_dword(0xcfc);}
void write32(function f,u16 offset,u32 value){if(offset>252)return;arch::out_dword(0xcf8,address(f,offset));arch::out_dword(0xcfc,value);}
u16 read16(function f,u16 offset){return u16(read32(f,offset)>>((offset&2)*8));}
void write16(function f,u16 offset,u16 value){if(offset>254 || (offset&1))return;arch::out_dword(0xcf8,address(f,offset));arch::out_word(u16(0xcfc+(offset&2)),value);}
bool find(u16 vendor,u16 device,function& result){
 for(u32 bus=0;bus<256;++bus)for(u8 slot=0;slot<32;++slot){
  function first{u8(bus),slot,0};if(u16(read32(first,0))==0xffff)continue;
  const u8 count=(read32(first,12)&0x800000u)?8:1;
  for(u8 fn=0;fn<count;++fn){function f{u8(bus),slot,fn};const auto id=read32(f,0);if(u16(id)==vendor && u16(id>>16)==device){result=f;return true;}}
 }
 return false;
}
bool memory_bar(function f,u8 index,bar& result){
 result={};if(index && !(read32(f,u16(12+index*4))&1) && ((read32(f,u16(12+index*4))>>1)&3)==2)return false;
 if(index>=6 || (read32(f,12)&0x7f0000u)!=0)return false;
 const u16 offset=u16(16+index*4);const u32 low=read32(f,offset);if(low&1)return false;
 const u32 type=(low>>1)&3;if(type!=0 && type!=2)return false;if(type==2 && index==5)return false;
 const u32 high=type==2?read32(f,offset+4):0;
 const u16 command=read16(f,4);write16(f,4,u16(command&~7u));
 write32(f,offset,0xffffffffu);if(type==2)write32(f,offset+4,0xffffffffu);
 const u32 mask_low=read32(f,offset)&~15u;const u32 mask_high=type==2?read32(f,offset+4):0xffffffffu;
 write32(f,offset,low);if(type==2)write32(f,offset+4,high);write16(f,4,command);
 const u64 base=(u64(high)<<32)|(low&~15u);u64 mask=(u64(mask_high)<<32)|mask_low;
 const u64 size=~mask+1;
 if(!base || !size || (size&(size-1)) || base<max_managed_phys || base>=0x100000000ull || size>0x100000000ull-base)return false;
 result={base,size,true};return true;
}
void* map_bar_range(const bar& b,u32 offset,u32 length){
 if(!b.memory || !length || offset>b.size || length>b.size-offset)return nullptr;
 const u64 physical=b.address+offset,first=physical&~(page_size-1),within=physical-first;
 const u64 bytes=(within+length+page_size-1)&~(page_size-1);
 if(bytes>0x33000000ull-next_mapping)return nullptr;
 const u64 begin=next_mapping;
 for(u64 i=0;i<bytes;i+=page_size){
  if(map_pci_device_page(begin+i,first+i)!=memory_result::none){for(u64 rollback=0;rollback<i;rollback+=page_size)(void)unmap_page(begin+rollback);return nullptr;}
 }
 next_mapping+=bytes;return reinterpret_cast<void*>(begin+within);
}
}

namespace xos::platform {
namespace {
struct reset_observer { u64 instance; volatile u8* status; };
reset_observer reset_observers[device_max_grants];
pci::function device_function(u64 instance) {
    const u32 bdf = static_cast<u32>(instance - 1);
    return {static_cast<u8>(bdf >> 8), static_cast<u8>((bdf >> 3) & 31), static_cast<u8>(bdf & 7)};
}
u16 capability(pci::function function, u8 wanted) {
    if (!(pci::read16(function, 6) & 0x10)) return 0;
    u16 offset = static_cast<u16>(pci::read32(function, 0x34) & 0xff);
    for (u32 count = 0; offset && count < 48; ++count) {
        if (offset < 0x40 || offset > 0xfc || (offset & 3)) return 0;
        const u32 header = pci::read32(function, offset);
        if (static_cast<u8>(header) == wanted) return offset;
        offset = static_cast<u16>((header >> 8) & 0xff);
    }
    return 0;
}
bool exclusive_irq(pci::function owner, u8 irq) {
    if (irq != 3 && irq != 5 && irq != 7 && irq != 9 && irq != 10 && irq != 11) return false;
    for (u32 bus = 0; bus < 256; ++bus) for (u8 slot = 0; slot < 32; ++slot) {
        pci::function first{static_cast<u8>(bus), slot, 0};
        if (static_cast<u16>(pci::read32(first, 0)) == 0xffff) continue;
        const u8 count = pci::read32(first, 12) & 0x800000 ? 8 : 1;
        for (u8 number = 0; number < count; ++number) {
            pci::function other{static_cast<u8>(bus), slot, number};
            if (other.bus == owner.bus && other.slot == owner.slot && other.number == owner.number) continue;
            if (static_cast<u16>(pci::read32(other, 0)) == 0xffff) continue;
            const u32 route = pci::read32(other, 0x3c);
            if ((route & 0xff00) && static_cast<u8>(route) == irq) return false;
        }
    }
    return true;
}
bool observe_supported_reset(u64 instance, pci::function function, const device_grants::description& resources) {
    const u32 identity = resources.configuration[0];
    const u16 product = static_cast<u16>(identity >> 16);
    if (static_cast<u16>(identity) != 0x1af4 || (product != 0x1000 && product != 0x1041)) return false;
    for (const auto& observer : reset_observers) if (observer.instance == instance) return true;
    reset_observer* available = nullptr;
    for (auto& observer : reset_observers) if (!observer.instance && !available) available = &observer;
    if (!available || !(pci::read16(function, 6) & 0x10)) return false;
    u32 offset = resources.configuration[0x34 / 4] & 0xff;
    for (u32 count = 0; offset && count < 48; ++count) {
        if (offset < 0x40 || offset > 0xf0 || (offset & 3)) return false;
        const u32 header = resources.configuration[offset / 4];
        if ((header & 0xff) == 9 && (header >> 24) == 1 && ((header >> 16) & 0xff) >= 16) {
            const u32 index = resources.configuration[offset / 4 + 1] & 0xff;
            const u64 start = resources.configuration[offset / 4 + 2];
            const u64 length = resources.configuration[offset / 4 + 3];
            if (index >= 6 || (start & 3) || length < 56 || start > resources.bars[index].length ||
                length > resources.bars[index].length - start) return false;
            const pci::bar bar{resources.bars[index].physical, resources.bars[index].length, true};
            auto* status = static_cast<volatile u8*>(pci::map_bar_range(bar, static_cast<u32>(start + 20), 1));
            if (!status) return false;
            *available = {instance, status}; return true;
        }
        offset = (header >> 8) & 0xff;
    }
    return false;
}
}

i64 device_inspect(u64 instance, u64 rights, device_grants::description& out) {
    out = {};
    const auto function = device_function(instance);
    const u32 identity = pci::read32(function, 0);
    if (static_cast<u16>(identity) == 0xffff) return device_no_device;
    // Display/storage remain kernel-owned. The first user-driver profile is an
    // unused network function; an executable name never enters this decision.
    if ((pci::read32(function, 8) >> 24) != 2 || (pci::read32(function, 12) & 0x7f0000)) return device_denied;
    if (pci::read16(function, 4) & 4) return device_busy;
    const u16 msi = capability(function, 5), msix = capability(function, 0x11);
    if (msi > 0xe8 || msix > 0xf4) return device_io;
    if ((msi && (pci::read16(function, msi + 2) & 1)) ||
        (msix && (pci::read16(function, msix + 2) & 0x8000))) return device_busy;
    bool mmio = false;
    for (u8 index = 0; index < 6; ++index) {
        pci::bar bar{};
        if (pci::memory_bar(function, index, bar) && !(bar.address & 4095) && !(bar.size & 4095)) {
            out.bars[index] = {bar.address, bar.size}; mmio = true;
        }
    }
    if ((rights & device_right_mmio) && !mmio) return device_no_device;
    const u32 route = pci::read32(function, 0x3c);
    out.irq = static_cast<u8>(route);
    out.irq_available = (route & 0xff00) && exclusive_irq(function, out.irq);
    if ((rights & device_right_irq) && !out.irq_available) return device_busy;
    for (u32 word = 0; word < 64; ++word) out.configuration[word] = pci::read32(function, static_cast<u16>(word * 4));
    // Discovery exposes BAR types and capability offsets, not physical bases.
    for (u32 word = 4; word < 10; ++word) out.configuration[word] &= 15;
    out.configuration[12] = 0;
    if (msi) {
        out.configuration[msi / 4 + 1] = 0;
        if ((pci::read16(function, msi + 2) & 0x80) && msi <= 0xf4) out.configuration[msi / 4 + 2] = 0;
    }
    if ((rights & device_right_dma) && !observe_supported_reset(instance, function, out)) return device_no_device;
    return 0;
}
bool device_memory_enable(u64 instance) {
    const auto function = device_function(instance);
    const u16 command = pci::read16(function, 4);
    pci::write16(function, 4, static_cast<u16>(command | 2));
    const u16 observed = pci::read16(function, 4);
    return observed != 0xffff && (observed & 2) != 0;
}
bool device_dma_start(u64 instance) {
    const auto function = device_function(instance);
    pci::write16(function, 4, static_cast<u16>(pci::read16(function, 4) | 6));
    const u16 command = pci::read16(function, 4);
    return command != 0xffff && (command & 6) == 6;
}
bool device_dma_stop(u64 instance) {
    const auto function = device_function(instance);
    pci::write16(function, 4, static_cast<u16>(pci::read16(function, 4) & ~4u));
    if (pci::read16(function, 4) & 4) return false;
    // VirtIO 1.2 §2.4.1 forbids queue interaction after reset status reaches 0.
    // The user driver performs reset; this narrow lifecycle observer only
    // reads its completion. BME/PCIe Transactions Pending alone is not proof.
    for (const auto& observer : reset_observers)
        if (observer.instance == instance) return *observer.status == 0;
    return false;
}
void device_disable(u64 instance) {
    const auto function = device_function(instance);
    pci::write16(function, 4, static_cast<u16>((pci::read16(function, 4) & ~6u) | 0x400));
}
bool device_irq_enable(u64 instance, u8 irq) {
    const auto function = device_function(instance);
    pci::write16(function, 4, static_cast<u16>(pci::read16(function, 4) & ~0x400u));
    const u16 command = pci::read16(function, 4);
    if (command == 0xffff || (command & 0x400)) return false;
    irq_unmask(irq);
    return true;
}
}
