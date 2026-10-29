// SPDX-License-Identifier: Apache-2.0
// Modern VirtIO PCI, split control queue, synchronous fenced 2D commands.
// This is a bounded PC/QEMU backend, not a compositor or 3D accelerator.
#include <xos/virtio_gpu.hpp>
#include <xos/pci.hpp>
#include <xos/memory.hpp>
#include <xos/format.hpp>
#ifndef XOS_VGPU_DMA_PAGE_LIMIT
#define XOS_VGPU_DMA_PAGE_LIMIT 512
#endif
#ifndef XOS_VGPU_POLL_LIMIT
#define XOS_VGPU_POLL_LIMIT 10000000
#endif
static_assert(__BYTE_ORDER__==__ORDER_LITTLE_ENDIAN__);
namespace xos::virtio_gpu {
namespace {
constexpr u32 width=800,height=600,frame_bytes=width*height*4,frame_pages=(frame_bytes+4095)/4096;
constexpr u16 queue_length=16;
struct [[gnu::packed]] header {u32 type,flags;u64 fence;u32 context;u8 ring,padding[3];};
struct [[gnu::packed]] descriptor {u64 address;u32 length;u16 flags,next;};
struct [[gnu::packed]] used_element {u32 id,length;};
struct [[gnu::packed]] create_request {header h;u32 resource,format,width,height;};
struct [[gnu::packed]] resource_request {header h;u32 resource,padding;};
struct [[gnu::packed]] scanout_request {header h;display_rect rect;u32 scanout,resource;};
struct [[gnu::packed]] transfer_request {header h;display_rect rect;u64 offset;u32 resource,padding;};
struct [[gnu::packed]] flush_request {header h;display_rect rect;u32 resource,padding;};
struct [[gnu::packed]] memory_entry {u64 address;u32 length,padding;};
static_assert(sizeof(header)==24 && sizeof(descriptor)==16 && sizeof(memory_entry)==16);
static_assert(sizeof(transfer_request)==56 && sizeof(create_request)==40);
volatile u8 *common,*notify,*device_config;
u32 notify_length,notify_multiplier;
volatile u16 *doorbell;
u64 ring_page,command_pages[2],response_page,pixels[frame_pages];
u32 pixel_count,dma_pages;
u16 available_index,used_index;
u64 next_fence,requests,completions;
u32 response_length;
bool transport,ready,failed;
pci::function function{};
alignas(8) u8 scratch[8192];
inline void barrier(){__asm__ volatile("mfence" ::: "memory");}
u8 read8(u32 offset){return common[offset];}
u16 read16(u32 offset){return *reinterpret_cast<volatile u16*>(common+offset);}
u32 read32(u32 offset){return *reinterpret_cast<volatile u32*>(common+offset);}
void write8(u32 offset,u8 value){common[offset]=value;barrier();}
void write16(u32 offset,u16 value){*reinterpret_cast<volatile u16*>(common+offset)=value;barrier();}
void write32(u32 offset,u32 value){*reinterpret_cast<volatile u32*>(common+offset)=value;barrier();}
void write64(u32 offset,u64 value){*reinterpret_cast<volatile u64*>(common+offset)=value;barrier();}
void log(const char* message){format::text("[virtio-gpu] ");format::text(message);format::text("\r\n");}
bool allocate(u64& page){if(dma_pages>=XOS_VGPU_DMA_PAGE_LIMIT || allocate_page(&page)!=memory_result::none)return false;++dma_pages;return true;}
void free_page(u64& page){if(page){(void)release_page(page);page=0;--dma_pages;}}
bool reset(){
 if(!common){return true;}write8(20,0);
 for(u32 i=0;i<1000000;++i){if(read8(20)==0){barrier();return true;}__asm__ volatile("pause");}
 log("reset_timeout DMA_pages_quarantined");return false;
}
void release(){
 ready=false;const u32 owned=dma_pages;const auto before_free=memory_status().free_pages;
 // Never return DMA pages to the allocator before the device acknowledges reset.
 if(!reset())return;
 for(auto& p:pixels){free_page(p);}pixel_count=0;
 free_page(response_page);free_page(command_pages[1]);free_page(command_pages[0]);free_page(ring_page);
 doorbell=nullptr;available_index=used_index=0;
 format::text("[virtio-gpu] DMA_released=");format::decimal(owned);format::text(" free_before=");format::decimal(before_free);format::text(" free_after=");format::decimal(memory_status().free_pages);format::text("\r\n");
}
bool probe(){
 if(transport)return true;
 if(!pci::find(0x1af4,0x1050,function))return false;
 format::text("[virtio-gpu] pci bus=");format::decimal(function.bus);format::text(" slot=");format::decimal(function.slot);format::text(" function=");format::decimal(function.number);format::text(" id=1af4:1050\r\n");
 if(!(pci::read16(function,6)&16))return false;
 pci::bar bars[6]{};bool checked[6]{};bool seen[256]{};
 u8 cap=u8(pci::read32(function,0x34)&0xfc);
 for(u32 count=0;cap && count<48;++count){
  if(cap<0x40 || cap>0xfc || seen[cap]){return false;}seen[cap]=true;
  const u32 first=pci::read32(function,cap);const u8 next=u8((first>>8)&0xfc),length=u8(first>>16),kind=u8(first>>24);
  if(u8(first)==9){
   if(length<16 || u32(cap)+length>256)return false;
   if(kind==1 || kind==2 || kind==4){
    const u8 bar=u8(pci::read32(function,cap+4));if(bar>=6)return false;
    if(!checked[bar]){if(!pci::memory_bar(function,bar,bars[bar]))return false;checked[bar]=true;}
    const u32 offset=pci::read32(function,cap+8),bytes=pci::read32(function,cap+12);
    const u32 minimum=kind==1?56:kind==4?16:2;
    if(bytes<minimum || (offset & (kind==2?1u:3u)))return false;
    auto* pointer=static_cast<volatile u8*>(pci::map_bar_range(bars[bar],offset,bytes));if(!pointer)return false;
    if(kind==1){if(common)return false;common=pointer;}
    else if(kind==2){if(notify || length<20)return false;notify=pointer;notify_length=bytes;notify_multiplier=pci::read32(function,cap+16);}
    else{if(device_config)return false;device_config=pointer;}
    format::text("[virtio-gpu] cap type=");format::decimal(kind);format::text(" bar=");format::decimal(bar);format::text(" physical=");format::hex(bars[bar].address+offset);format::text(" length=");format::decimal(bytes);format::text(" kernel_only=1\r\n");
   }
  }
  cap=next;
 }
 if(!common || !notify || !device_config)return false;
 // MMIO decoding and bus mastering; disable unused INTx, poll the bounded queue.
 pci::write16(function,4,u16(pci::read16(function,4)|0x406));transport=true;return true;
}
bool configure_queue(){
 if(!reset()){return false;}failed=false;available_index=used_index=0;next_fence=0;
 write8(20,1);write8(20,3);
 write32(0,1);const u32 high=read32(4);if(!(high&1)){log("VERSION_1_missing");return false;}
 write32(8,0);write32(12,0);write32(8,1);write32(12,1);
 write8(20,11);if(!(read8(20)&8)){log("features_rejected");return false;}
 if(read16(18)<1)return false;
 write16(22,0);if(read16(24)<queue_length || read16(28)!=0)return false;
 if(!allocate(ring_page) || !allocate(command_pages[0]) || !allocate(command_pages[1]) || !allocate(response_page))return false;
 write16(24,queue_length);if(read16(24)!=queue_length)return false;write16(26,0xffff);
 const u64 location=u64(read16(30))*notify_multiplier;if(location>notify_length || notify_length-location<2 || (location&1))return false;
 doorbell=reinterpret_cast<volatile u16*>(notify+location);
 *reinterpret_cast<volatile u16*>(ring_page+256)=1; // suppress queue interrupts
 write64(32,ring_page);write64(40,ring_page+256);write64(48,ring_page+512);write16(28,1);if(read16(28)!=1)return false;
 write8(20,15);if(read8(20)!=15)return false;
 format::text("[virtio-gpu] negotiated VERSION_1 queue=0 length=16 ring_phys=");format::hex(ring_page);format::text(" polling=1\r\n");return true;
}
header* begin(u32 type,u32 length){
 if(length>sizeof(scratch) || length<sizeof(header))return nullptr;
 for(u32 i=0;i<length;++i)scratch[i]=0;
 auto* h=reinterpret_cast<header*>(scratch);h->type=type;h->flags=1;h->fence=++next_fence;return h;
}
u32 submit(u32 length){
 if(failed || !doorbell || length<sizeof(header) || length>sizeof(scratch))return 0;
 const auto fence=reinterpret_cast<header*>(scratch)->fence;
 for(u32 i=0;i<length;++i)reinterpret_cast<u8*>(command_pages[i/4096])[i%4096]=scratch[i];
 auto* descriptors=reinterpret_cast<volatile descriptor*>(ring_page);
 descriptors[0].address=command_pages[0];descriptors[0].length=length>4096?4096:length;descriptors[0].flags=1;descriptors[0].next=length>4096?1:2;
 if(length>4096){descriptors[1].address=command_pages[1];descriptors[1].length=length-4096;descriptors[1].flags=1;descriptors[1].next=2;}
 descriptors[2].address=response_page;descriptors[2].length=4096;descriptors[2].flags=2;descriptors[2].next=0;
 auto* response=reinterpret_cast<volatile header*>(response_page);response->type=0;response->flags=0;response->fence=0;
 auto* avail=reinterpret_cast<volatile u16*>(ring_page+256);avail[2+(available_index%queue_length)]=0;
 barrier();avail[1]=++available_index;barrier();*doorbell=0;++requests;
 auto* used=reinterpret_cast<volatile u16*>(ring_page+512);
 bool complete=false;
 for(u32 remaining=XOS_VGPU_POLL_LIMIT;remaining!=0;--remaining){if(used[1]!=used_index){complete=true;break;}__asm__ volatile("pause" ::: "memory");}
 barrier();
 if(!complete){failed=true;ready=false;log("queue_timeout");return 0;}
 auto* elements=reinterpret_cast<volatile used_element*>(ring_page+516);
 const auto& item=elements[used_index%queue_length];
 if(u16(used[1]-used_index)!=1 || item.id!=0 || item.length<sizeof(header) || item.length>4096 || response->flags!=1 || response->fence!=fence){failed=true;ready=false;log("invalid_completion");return 0;}
 response_length=item.length;++used_index;++completions;return response->type;
}
bool create(u32 id){auto* c=reinterpret_cast<create_request*>(begin(0x101,sizeof(create_request)));c->resource=id;c->format=2;c->width=width;c->height=height;return submit(sizeof(*c))==0x1100;}
bool resource(u32 type,u32 id){auto* c=reinterpret_cast<resource_request*>(begin(type,sizeof(resource_request)));c->resource=id;return submit(sizeof(*c))==0x1100;}
bool attach(u32 id){
 const u32 length=32+pixel_count*u32(sizeof(memory_entry));auto* h=begin(0x106,length);if(!h)return false;
 auto* fields=reinterpret_cast<u32*>(scratch+24);fields[0]=id;fields[1]=pixel_count;
 auto* entries=reinterpret_cast<memory_entry*>(scratch+32);
 for(u32 i=0;i<pixel_count;++i)entries[i]={pixels[i],i+1==pixel_count?frame_bytes-i*4096:4096,0};
 return submit(length)==0x1100;
}
bool scanout(u32 id){auto* c=reinterpret_cast<scanout_request*>(begin(0x103,sizeof(scanout_request)));c->rect=id?display_rect{0,0,width,height}:display_rect{};c->scanout=0;c->resource=id;return submit(sizeof(*c))==0x1100;}
bool update(u32 id,display_rect rect){
 auto* t=reinterpret_cast<transfer_request*>(begin(0x105,sizeof(transfer_request)));t->rect=rect;t->offset=(u64(rect.y)*width+rect.x)*4;t->resource=id;
 if(submit(sizeof(*t))!=0x1100)return false;
 auto* f=reinterpret_cast<flush_request*>(begin(0x104,sizeof(flush_request)));f->rect=rect;f->resource=id;return submit(sizeof(*f))==0x1100;
}
bool valid_rect(display_rect r){return r.width && r.height && r.x<width && r.y<height && r.width<=width-r.x && r.height<=height-r.y;}
}
bool init(){
 if(ready){return true;}if(dma_pages){log("old_DMA_ownership_retained");return false;}
 if(!probe())return false;
 if(!configure_queue()){log("queue_init_failed");release();return false;}
 bool stable=false;u32 scanouts=0;
 for(u32 attempt=0;attempt<8;++attempt){const auto generation=read8(21);scanouts=*reinterpret_cast<volatile u32*>(device_config+8);barrier();if(generation==read8(21)){stable=scanouts>0 && scanouts<=16;break;}}
 if(!stable){log("device_config_unstable_or_invalid");release();return false;}
 format::text("[virtio-gpu] display_config scanouts=");format::decimal(scanouts);format::text("\r\n");
 auto* h=begin(0x100,sizeof(header));(void)h;
 if(submit(sizeof(header))!=0x1101 || response_length<24+16*24){log("display_info_failed");release();return false;}
 const auto* info=reinterpret_cast<const u32*>(response_page+24);
 if(!info[4] || !info[2] || !info[3]){log("scanout0_unavailable");release();return false;}
 for(u32 i=0;i<frame_pages;++i){if(!allocate(pixels[i])){log("DMA_budget_or_memory_exhausted");release();return false;}++pixel_count;}
 if(!create(1) || !attach(1) || !scanout(1) || !update(1,{0,0,width,height})){log("resource_init_failed");release();return false;}
 ready=true;log("ready backend=2d format=B8G8R8X8 width=800 height=600");
 format::text("[virtio-gpu] backing_pages=");format::decimal(pixel_count);format::text(" dma_pages=");format::decimal(dma_pages);format::text(" requests=");format::decimal(requests);format::text(" completions=");format::decimal(completions);format::text("\r\n");return true;
}
bool available(){return ready && !failed;}
display_mode mode(){return {1,sizeof(display_mode),width,height,width*4,display_xrgb8888,frame_bytes};}
void write(u64 offset,const u8* bytes,u64 length){
 if(!available() || offset>frame_bytes || length>frame_bytes-offset)return;
 while(length){const u64 page=offset/4096,in_page=offset%4096,n=length<4096-in_page?length:4096-in_page;auto* destination=reinterpret_cast<u8*>(pixels[page]+in_page);for(u64 i=0;i<n;++i)destination[i]=bytes[i];offset+=n;bytes+=n;length-=n;}
}
bool present(display_rect rect){
 if(!available() || !valid_rect(rect))return false;
 if(!update(1,rect)){ready=false;log("present_failed");release();return false;}
 format::text("[virtio-gpu-frame] x=");format::decimal(rect.x);format::text(" y=");format::decimal(rect.y);format::text(" w=");format::decimal(rect.width);format::text(" h=");format::decimal(rect.height);format::text(" requests=");format::decimal(requests);format::text(" completed=");format::decimal(completions);format::text("\r\n");return true;
}
bool self_test(){
 if(!available()){log("selftest unavailable");return false;}
 const auto before=memory_status().free_pages;const auto initial=requests;
 const bool bounds=!present({width,0,1,1}) && !present({0,0,0,1}) && requests==initial;
 auto* bad=reinterpret_cast<resource_request*>(begin(0x102,sizeof(resource_request)));bad->resource=0xfffffffeu;const auto response=submit(sizeof(*bad));
 begin(0xffff,sizeof(header));const auto unknown=submit(sizeof(header));
 auto* rectangle=reinterpret_cast<transfer_request*>(begin(0x105,sizeof(transfer_request)));rectangle->rect={width,0,1,1};rectangle->resource=1;const auto bad_rect=submit(sizeof(*rectangle));
 format::text("[virtio-gpu] negative bad_resource=");format::hex(response);format::text(" unknown_command=");format::hex(unknown);format::text(" bad_rect=");format::hex(bad_rect);format::text("\r\n");
 bool ok=bounds && response==0x1203 && unknown==0x1200 && bad_rect==0x1205;
 for(u32 i=0;i<3 && ok;++i)ok=create(2) && attach(2) && scanout(2) && update(2,{0,0,width,height}) && scanout(1) && resource(0x107,2) && resource(0x102,2);
 ok=ok && memory_status().free_pages==before;
 release();const auto reclaimed=memory_status().free_pages;ok=ok && dma_pages==0 && init() && memory_status().free_pages==before;
 format::text("[virtio-gpu] selftest bounds_invalid_resource_cycles_reset=");format::text(ok?"pass":"fail");format::text(" baseline_free=");format::decimal(before);format::text(" after_release_free=");format::decimal(reclaimed);format::text(" after_reinit_free=");format::decimal(memory_status().free_pages);format::text(" requests=");format::decimal(requests);format::text(" completions=");format::decimal(completions);format::text("\r\n");return ok;
}
bool resource_limit_test(){
 if(!available())return false;
 auto* c=reinterpret_cast<create_request*>(begin(0x101,sizeof(create_request)));c->resource=2;c->format=2;c->width=width;c->height=height;
 const auto result=submit(sizeof(*c));if(result==0x1100)(void)resource(0x102,2);
 format::text("[virtio-gpu] host_resource_limit response=");format::hex(result);format::text(" ready=");format::decimal(available()?1:0);format::text("\r\n");return result==0x1201 && available();
}
}
