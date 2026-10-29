// SPDX-License-Identifier: Apache-2.0
// Modern VirtIO-Net: private kernel-owned Ethernet mechanism, no TCP/IP policy.
#include <xos/virtio_net.hpp>
#include <xos/pci.hpp>
#include <xos/memory.hpp>
#include <xos/format.hpp>
#include "arch/x86_64/pic.hpp"
#include "arch/x86_64/io.hpp"
#ifndef XOS_VNET_DMA_PAGE_LIMIT
#define XOS_VNET_DMA_PAGE_LIMIT 34
#endif
namespace xos::virtio_net {
namespace {
constexpr u16 capacity=16,header_bytes=12,maximum_frame=1514;
struct [[gnu::packed]] descriptor {u64 address;u32 length;u16 flags,next;};
struct [[gnu::packed]] used_element {u32 id,length;};
struct queue {u64 ring,pages[capacity];volatile u16* doorbell;u16 available,used;bool owned[capacity];};
static_assert(sizeof(descriptor)==16 && sizeof(used_element)==8);
static_assert(__BYTE_ORDER__==__ORDER_LITTLE_ENDIAN__);
pci::function function{};
volatile u8 *common,*notify,*isr,*configuration;
u32 notify_bytes,multiplier,dma_pages;
queue rx{},tx{};
u8 irq_line,old_elcr,old_master_mask,old_slave_mask;
u16 old_command;
bool mapped,probe_attempted,live,broken,route_enabled;
u64 interrupts,spurious,received,transmitted,rejected,dropped;
struct frame {u16 length;u8 data[maximum_frame];};
frame pending[capacity];
u16 pending_begin,pending_count;
u8 rejected_header[12]{};
inline void barrier(){__asm__ volatile("mfence" ::: "memory");}
u8 r8(u32 n){return common[n];}
u16 r16(u32 n){return *reinterpret_cast<volatile u16*>(common+n);}
u32 r32(u32 n){return *reinterpret_cast<volatile u32*>(common+n);}
void w8(u32 n,u8 v){common[n]=v;barrier();}
void w16(u32 n,u16 v){*reinterpret_cast<volatile u16*>(common+n)=v;barrier();}
void w32(u32 n,u32 v){*reinterpret_cast<volatile u32*>(common+n)=v;barrier();}
void w64(u32 n,u64 v){*reinterpret_cast<volatile u64*>(common+n)=v;barrier();}
void log(const char* s){format::text("[virtio-net] ");format::text(s);format::text("\r\n");}
void number(const char* s,u64 n){format::text(s);format::decimal(n);}
bool allocate(u64& p){if(dma_pages>=XOS_VNET_DMA_PAGE_LIMIT || allocate_page(&p)!=memory_result::none)return false;++dma_pages;return true;}
void free_page(u64& p){if(p){(void)release_page(p);p=0;--dma_pages;}}
bool reset(){
 if(!common)return true;
 w8(20,0);
 for(u32 i=0;i<1000000;++i){if(r8(20)==0){barrier();return true;}__asm__ volatile("pause");}
 log("reset_timeout DMA_quarantined=1");return false;
}
void fail(){broken=true;live=false;pci::write16(function,4,u16(pci::read16(function,4)|0x400));}
bool release(){
 live=false;
 if(route_enabled){arch::pic_line_enable(irq_line,false);const u16 port=irq_line<8?0x4d0:0x4d1;arch::out_byte(port,old_elcr);arch::out_byte(0x21,old_master_mask);arch::out_byte(0xa1,old_slave_mask);route_enabled=false;}
 if(!reset())return false;
 for(auto& p:rx.pages){free_page(p);}free_page(rx.ring);rx={};
 for(auto& p:tx.pages){free_page(p);}free_page(tx.ring);tx={};
 pending_begin=pending_count=0;
 if(mapped)pci::write16(function,4,old_command);
 return dma_pages==0;
}
bool probe(){
 if(mapped)return true;
 if(probe_attempted)return false;
 probe_attempted=true;
 if(!pci::find(0x1af4,0x1041,function)){log("absent modern_id=1af4:1041");return false;}
 // Type-0 Ethernet controller only; do not accept a vendor match alone.
 if((pci::read32(function,8)>>16)!=0x0200 || (pci::read32(function,12)&0x7f0000u)!=0 || !(pci::read16(function,6)&16))return false;
 const u32 interrupt=pci::read32(function,0x3c);irq_line=u8(interrupt);
 if(u8(interrupt>>8)<1 || u8(interrupt>>8)>4 || (irq_line!=5 && irq_line!=9 && irq_line!=10 && irq_line!=11)){log("unsupported_INTx_route");return false;}
 pci::bar bars[6]{};bool checked[6]{},seen[256]{};u8 cap=u8(pci::read32(function,0x34)&0xfc);
 for(u32 count=0;cap && count<48;++count){
  if(cap<0x40 || cap>0xfc || seen[cap]){return false;}seen[cap]=true;
  const u32 first=pci::read32(function,cap);const u8 next=u8((first>>8)&0xfc),length=u8(first>>16),kind=u8(first>>24);
  if(u8(first)==9 && kind>=1 && kind<=4){
   if(length<16 || u32(cap)+length>256)return false;
   const u8 bar=u8(pci::read32(function,cap+4));if(bar>=6)return false;
   if(!checked[bar]){if(!pci::memory_bar(function,bar,bars[bar]))return false;checked[bar]=true;}
   const u32 offset=pci::read32(function,cap+8),bytes=pci::read32(function,cap+12);
   const u32 minimum=kind==1?56:kind==2?2:kind==3?1:6;
   if(bytes<minimum || (offset & (kind==2?1u:kind==1?3u:0u)))return false;
   auto* ptr=static_cast<volatile u8*>(pci::map_bar_range(bars[bar],offset,bytes));if(!ptr)return false;
   if(kind==1){if(common)return false;common=ptr;}
   if(kind==2){if(notify || length<20)return false;notify=ptr;notify_bytes=bytes;multiplier=pci::read32(function,cap+16);}
   if(kind==3){if(isr)return false;isr=ptr;}
   if(kind==4){if(configuration)return false;configuration=ptr;}
  }
  cap=next;
 }
 if(cap || !common || !notify || !isr || !configuration)return false;
 old_command=pci::read16(function,4);pci::write16(function,4,u16((old_command|6u)&~0x400u));mapped=true;
 format::text("[virtio-net] pci id=1af4:1041");number(" bus=",function.bus);number(" slot=",function.slot);number(" irq=",irq_line);format::text(" kernel_only=1\r\n");return true;
}
volatile descriptor* descriptors(queue& q){return reinterpret_cast<volatile descriptor*>(q.ring);}
volatile u16* available(queue& q){return reinterpret_cast<volatile u16*>(q.ring+256);}
volatile u16* used(queue& q){return reinterpret_cast<volatile u16*>(q.ring+512);}
void publish(queue& q,u16 id){auto* a=available(q);a[2+(q.available%capacity)]=id;barrier();q.available=u16(q.available+1);a[1]=q.available;barrier();}
void kick(queue& q,u16 index){barrier();*q.doorbell=index;}
bool configure(queue& q,u16 index){
 w16(22,index);if(r16(24)<capacity || r16(28))return false;
 if(!allocate(q.ring))return false;
 for(auto& page:q.pages)if(!allocate(page))return false;
 w16(24,capacity);w16(26,0xffff);if(r16(24)!=capacity)return false;
 const u64 offset=u64(r16(30))*multiplier;if(offset>notify_bytes || notify_bytes-offset<2 || (offset&1))return false;
 q.doorbell=reinterpret_cast<volatile u16*>(notify+offset);
 w64(32,q.ring);w64(40,q.ring+256);w64(48,q.ring+512);
 if(index==0)for(u16 i=0;i<capacity;++i){auto& d=descriptors(q)[i];d.address=q.pages[i];d.length=4096;d.flags=2;d.next=0;q.owned[i]=true;publish(q,i);}
 w16(28,1);return r16(28)==1;
}
bool init(){
 if(dma_pages || !probe() || !reset())return false;
 broken=false;pending_begin=pending_count=0;interrupts=spurious=received=transmitted=rejected=dropped=0;
 // MMIO decode/bus master re-enabled after a prior diagnostic release.
 pci::write16(function,4,u16((old_command|6u)&~0x400u));w8(20,1);w8(20,3);
 w32(0,0);const auto low=r32(4);w32(0,1);const auto high=r32(4);
 if(!(high&1) || (low&((1u<<5)|(1u<<15)))!=((1u<<5)|(1u<<15))){log("required_VERSION_1_MAC_MRG_missing");release();return false;}
 w32(8,0);w32(12,(1u<<5)|(1u<<15));w32(8,1);w32(12,1);w8(20,11);
 if(!(r8(20)&8) || r16(18)<2 || !configure(rx,0) || !configure(tx,1)){log("features_queue_or_DMA_failure");release();return false;}
 bool stable=false;u8 mac[6]{};
 for(u32 n=0;n<8;++n){const auto gen=r8(21);for(u32 i=0;i<6;++i)mac[i]=configuration[i];barrier();if(gen==r8(21)){stable=true;break;}}
 if(!stable || (mac[0]&1)){release();return false;}
 old_master_mask=arch::in_byte(0x21);old_slave_mask=arch::in_byte(0xa1);
 if(!((irq_line<8?old_master_mask:old_slave_mask)&(1u<<(irq_line&7)))){log("diagnostic_IRQ_already_unmasked");release();return false;}
 const u16 port=irq_line<8?0x4d0:0x4d1;old_elcr=arch::in_byte(port);route_enabled=true;arch::out_byte(port,u8(old_elcr|(1u<<(irq_line&7))));
 if(!(arch::in_byte(port)&(1u<<(irq_line&7)))){release();return false;}
 route_enabled=true;live=true;w8(20,15);arch::pic_line_enable(irq_line,true);kick(rx,0);
 format::text("[virtio-net] ready VERSION_1 MAC MRG_RXBUF single_buffer MTU=1500 RX=16 TX=16");number(" dma_pages=",dma_pages);number(" INTx=",irq_line);format::text(" level=1 polling_idle=0\r\n");return true;
}
// Called with interrupts disabled; all accesses are serialized on the qualified single CPU.
i32 send(const u8* data,u32 length){
 if(!live || broken)return -19;
 if(!data || length<14 || length>maximum_frame)return -22;
 u16 id=capacity;for(u16 i=0;i<capacity;++i)if(!tx.owned[i]){id=i;break;}if(id==capacity)return -11;
 auto* target=reinterpret_cast<u8*>(tx.pages[id]);for(u32 i=0;i<header_bytes;++i)target[i]=0;for(u32 i=0;i<length;++i)target[header_bytes+i]=data[i];
 auto& d=descriptors(tx)[id];d.address=tx.pages[id];d.length=header_bytes+length;d.flags=0;d.next=0;tx.owned[id]=true;publish(tx,id);kick(tx,1);return i32(length);
}
void consume(queue& q,bool receive){
 const u16 next=used(q)[1];barrier();if(u16(next-q.used)>capacity){fail();return;}
 auto* elements=reinterpret_cast<volatile used_element*>(q.ring+516);u16 seen=0;
 for(u16 n=0;q.used!=next && n<capacity;++n){
  const auto& item=elements[q.used%capacity];const u32 id=item.id,length=item.length;
  if(id>=capacity || (seen&(1u<<id)) || !q.owned[id] || (receive?length>4096:length!=0)){fail();return;}
  seen=u16(seen|(1u<<id));q.owned[id]=false;q.used=u16(q.used+1);
  if(receive){
   auto* data=reinterpret_cast<const u8*>(q.pages[id]);
   if(length>=header_bytes && (data[10]>1 || data[11])){fail();return;}
   if(length<header_bytes+14 || length>header_bytes+maximum_frame || data[0] || data[1] || data[10]!=1 || data[11]){for(u32 h=0;h<12;++h)rejected_header[h]=data[h];++rejected;}
   else if(pending_count==capacity){++dropped;}
   else{auto& f=pending[(pending_begin+pending_count)%capacity];f.length=u16(length-header_bytes);for(u32 i=0;i<f.length;++i)f.data[i]=data[header_bytes+i];++pending_count;++received;}
   // The device owns this page again only after the bounded copy/drop is complete.
   q.owned[id]=true;publish(q,u16(id));
  }else ++transmitted;
 }
 if(receive && !broken)kick(q,0);
}
bool wait_until(u64 rx_count,u64 tx_count,u64 ticks){
 const auto deadline=arch::pic_ticks()+ticks;
 while(!broken && (received<rx_count || transmitted<tx_count) && arch::pic_ticks()<deadline){__asm__ volatile("sti; hlt; cli" ::: "memory");}
 return !broken && received>=rx_count && transmitted>=tx_count;
}
void pattern(u8* data,u32 length,u8 sequence){
 for(u32 i=0;i<6;++i)data[i]=0xff;
 const u8 mac[6]={0x52,0x54,0,0x12,0x34,0x56};for(u32 i=0;i<6;++i)data[6+i]=mac[i];
 data[12]=0x88;data[13]=0xb5;for(u32 i=14;i<length;++i)data[i]=u8(i+sequence);data[14]=sequence;
}
}
void interrupt(u8 irq){
 if(!mapped || irq!=irq_line || !live)return;
 const auto cause=*isr;barrier();if(!cause){++spurious;return;}++interrupts;
 if((cause&2) || (r8(20)&64)){fail();return;}
 if(cause&1){consume(tx,false);if(!broken)consume(rx,true);}
}
bool self_test(u32 profile){
 const bool echo_expected=profile==0 || profile==2;
 // Explicit C26 diagnostic before scheduler entry. It always quiesces on return.
 // The existing boot monitor itself polls UART; network waiting uses PIT/INTx HLT.
 arch::pic_init();arch::timer_init(100);
 const auto before=memory_status().free_pages;
 if(!init())return false;
 const auto baseline=memory_status().free_pages;bool ok=true;u8 bytes[maximum_frame];
 pattern(bytes,60,0);ok=send(bytes,13)==-22 && send(bytes,1515)==-22;
 for(u16 i=0;i<capacity && ok;++i){const u32 length=i==15?1514:u32(60+i*23);pattern(bytes,length,u8(i));ok=send(bytes,length)==i32(length);}
 ok=ok && send(bytes,60)==-11;
 log("submitted=16 queue_backpressure=AGAIN invalid_lengths=INVALID waiting=HLT");
 const bool completed=wait_until(echo_expected?16:1,16,echo_expected?500:30);
 if(profile==2){const auto end=arch::pic_ticks()+20;while(!broken && arch::pic_ticks()<end){__asm__ volatile("sti; hlt; cli" ::: "memory");}}
 if(echo_expected){
  ok=ok && completed && pending_count==16;
  u16 seen=0;
  while(pending_count){const auto& f=pending[pending_begin];const u8 seq=f.data[14];const u32 length=seq==15?1514:u32(60+seq*23);if(seq>=16 || f.length!=length || (seen&(1u<<seq))){ok=false;break;}
   pattern(bytes,length,seq);for(u32 i=0;i<length;++i)if(f.data[i]!=bytes[i])ok=false;seen=u16(seen|(1u<<seq));pending_begin=u16((pending_begin+1)%capacity);--pending_count;
  }
  ok=ok && seen==0xffff;
  if(profile==2)ok=ok && dropped==8;
 }else if(profile==3)ok=ok && broken && !completed;
 else ok=ok && !completed && received==0 && transmitted==16;
 format::text("[virtio-net] test");number(" rx=",received);number(" tx_completed=",transmitted);number(" irqs=",interrupts);number(" rejected=",rejected);number(" dropped=",dropped);number(" failed=",broken?1:0);number(" live_dma=",dma_pages);format::text(" rejected_header=");for(auto h:rejected_header){format::hex(h);format::text(" ");}format::text("\r\n");
 ok=ok && interrupts>0 && memory_status().free_pages==baseline;
 const u32 owned=dma_pages;ok=release() && ok;
 const auto after=memory_status().free_pages;
 // First PCI mapping may allocate bounded infrastructure page tables; DMA exactness is independent.
 ok=ok && after==baseline+owned;
 format::text("[virtio-net] reset");number(" reclaimed=",owned);number(" before=",before);number(" baseline=",baseline);number(" after=",after);format::text(ok?" result=pass\r\n":" result=fail\r\n");
 return ok;
}
}
namespace xos::platform {void device_irq(u8 irq){virtio_net::interrupt(irq);}}
