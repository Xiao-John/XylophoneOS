// SPDX-License-Identifier: Apache-2.0
// PC configuration mechanism #1. Boot/debug discovery only; no hotplug/SMP claim.
#include <xos/pci.hpp>
#include <xos/memory.hpp>
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
