// SPDX-License-Identifier: Apache-2.0
#include <xos/display.hpp>
#include <xos/memory.hpp>
#include <xos/format.hpp>
#include <xos/virtio_gpu.hpp>
namespace xos::display {
namespace { display_mode screen{}; volatile u8* framebuffer; bool gpu_selected; }
static void init_vbe(const boot_info& info) {
    if (info.version != boot_display_version || info.size != boot_info_display_size) { return; }
    const auto& d=*reinterpret_cast<const boot_display*>(&info+1);
    if (d.status!=1 || d.version!=1 || d.size!=sizeof(boot_display) || d.reserved!=0 ||
        d.format!=display_xrgb8888 || d.width<1 || d.width>800 || d.height<1 || d.height>600 ||
        d.stride<d.width*4 || d.stride>4096 || d.bytes!=u64{d.stride}*d.height ||
        d.physical<max_managed_phys || d.physical>=0x100000000ull ||
        d.bytes>0x100000000ull-d.physical) {
        format::text("[display] state=absent_or_unsupported\r\n"); return;
    }
    const u64 physical=d.physical&~(page_size-1), offset=d.physical-physical;
    for (u64 i=0;i<d.bytes+offset;i+=page_size) {
        if (map_device_page(0x30000000ull+i,physical+i)!=memory_result::none) {
            format::text("[display] state=mapping_failed\r\n"); return;
        }
    }
    framebuffer=reinterpret_cast<volatile u8*>(0x30000000ull+offset);
    screen={1,sizeof(display_mode),d.width,d.height,d.stride,d.format,d.bytes};
    format::text("[display] state=ready width="); format::decimal(d.width);
    format::text(" height="); format::decimal(d.height); format::text(" stride=");
    format::decimal(d.stride); format::text(" physical="); format::hex(d.physical);
    format::text(" bytes="); format::decimal(d.bytes); format::text(" cache=uc user_mapping=none\r\n");
}
void init(const boot_info& info){
    init_vbe(info);
    if(virtio_gpu::init()){gpu_selected=true;screen=virtio_gpu::mode();format::text("[display] backend=virtio-gpu-2d user_mapping=none\r\n");}
    else if(framebuffer){format::text("[display] backend=vbe fallback=1\r\n");}
}
bool available(){return gpu_selected?virtio_gpu::available():framebuffer!=nullptr;}
display_mode mode(){return screen;}
bool valid(const display_present& p) {
    return available() && p.version==1 && p.size==sizeof(p) && p.format==screen.format &&
        p.stride>=screen.width*4 && p.stride<=4096 && p.length==u64{p.stride}*screen.height &&
        p.rect.width!=0 && p.rect.height!=0 && p.rect.x<screen.width && p.rect.y<screen.height &&
        p.rect.width<=screen.width-p.rect.x && p.rect.height<=screen.height-p.rect.y;
}
void write(u64 offset,const u8* bytes,u64 length){
    if (!available() || offset>screen.bytes || length>screen.bytes-offset) {return;}
    if(gpu_selected){virtio_gpu::write(offset,bytes,length);return;}
    for(u64 i=0;i<length;++i){framebuffer[offset+i]=bytes[i];}
    __asm__ volatile("sfence" ::: "memory");
}
bool commit(display_rect rect){return gpu_selected?virtio_gpu::present(rect):available();}
}
