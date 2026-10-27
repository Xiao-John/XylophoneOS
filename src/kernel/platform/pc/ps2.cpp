// SPDX-License-Identifier: Apache-2.0
#include <xos/display.hpp>
#include <xos/format.hpp>
#include "arch/x86_64/io.hpp"
#include "arch/x86_64/pic.hpp"
namespace xos::display {
namespace {
display_event queue[display_event_capacity];
u32 head,count,lost,modifiers,buttons;
u64 sequence;
i32 x,y;
bool focused,extended;
u8 pause_bytes,packet[3],packet_index;
bool keys[512];
bool writable(){
    for(u32 i=0;i<65536;++i){if((arch::in_byte(0x64)&2)==0){return true;}}
    return false;
}
bool command(u8 value){if(!writable()){return false;}arch::out_byte(0x64,value);return true;}
bool data(u8 value){if(!writable()){return false;}arch::out_byte(0x60,value);return true;}
bool response(u8& value){
    for(u32 i=0;i<65536;++i){
        const u8 status=arch::in_byte(0x64);
        if((status&1)!=0){value=arch::in_byte(0x60);return (status&0xc0)==0;}
    }return false;
}
bool mouse_command(u8 value){
    u8 ack=0;
    return command(0xd4)&&data(value)&&response(ack)&&ack==0xfa;
}
void enqueue(display_event event){
    if(!focused){return;}
    event.sequence=++sequence;event.modifiers=modifiers;event.buttons=buttons;
    event.x=x;event.y=y;
    if(count==display_event_capacity){
        lost+=count+1;head=0;count=0;
        event.kind=4;event.code=0;event.dx=0;event.dy=0;event.lost=lost;
    }
    queue[(head+count)%display_event_capacity]=event;++count;
}
void keyboard(u8 value,u64 now){
    if(value==0xfa || value==0xfe){return;}
    if(pause_bytes!=0){--pause_bytes;return;}
    if(value==0xe1){pause_bytes=5;return;}
    if(value==0xe0){extended=true;return;}
    const u32 code=(value&0x7fu)|(extended?0x100u:0u);extended=false;
    const bool down=(value&0x80)==0;
    const bool previous=keys[code];keys[code]=down;
    if(code==0x3a && down && !previous){modifiers^=8;}
    modifiers=(modifiers&8u)|((keys[0x2a]||keys[0x36])?1u:0u)|
        ((keys[0x1d]||keys[0x11d])?2u:0u)|((keys[0x38]||keys[0x138])?4u:0u);
    display_event event{};event.kind=down?1u:2u;event.code=code;event.monotonic_ns=now;
    enqueue(event);
}
void mouse(u8 value,u64 now){
    if(packet_index==0 && (value&8)==0){return;}
    packet[packet_index++]=value;
    if(packet_index!=3){return;}packet_index=0;
    if((packet[0]&0xc0)!=0){return;}
    const i32 dx=static_cast<i32>(packet[1])-((packet[0]&0x10)!=0?256:0);
    const i32 dy=-(static_cast<i32>(packet[2])-((packet[0]&0x20)!=0?256:0));
    x+=dx;y+=dy;
    const auto screen=mode();
    if(x<0){x=0;}if(y<0){y=0;}
    if(screen.width!=0 && x>=static_cast<i32>(screen.width)){x=static_cast<i32>(screen.width)-1;}
    if(screen.height!=0 && y>=static_cast<i32>(screen.height)){y=static_cast<i32>(screen.height)-1;}
    buttons=packet[0]&7u;
    display_event event{};event.kind=3;event.dx=dx;event.dy=dy;event.monotonic_ns=now;
    enqueue(event);
}
}
void input_reset(bool active){
    focused=active;head=0;count=0;lost=0;modifiers=0;buttons=0;
    extended=false;pause_bytes=0;packet_index=0;
    for(auto& key:keys){key=false;}
    x=static_cast<i32>(mode().width/2);y=static_cast<i32>(mode().height/2);
}
bool input_pending(){return count!=0;}
bool input_read(display_event& event){
    if(count==0){return false;}event=queue[head];head=(head+1)%display_event_capacity;--count;return true;
}
void input_init(){
    bool ok=command(0xad)&&command(0xa7);
    for(u32 i=0;i<64 && (arch::in_byte(0x64)&1)!=0;++i){(void)arch::in_byte(0x60);}
    u8 config=0;
    ok=ok&&command(0x20)&&response(config);
    ok=ok&&command(0x60)&&data(static_cast<u8>((config|0x43u)&~0x30u));
    ok=ok&&command(0xae)&&command(0xa8);
    u8 ack=0;
    ok=ok&&data(0xf4)&&response(ack)&&ack==0xfa;
    ok=ok&&mouse_command(0xf6)&&mouse_command(0xf4);
    if(ok){arch::pic_input_enable();}
    input_reset(false);
    format::text(ok?"[input] ps2=ready irq1=enabled irq12=enabled\r\n":
        "[input] ps2=failed irqs=masked\r\n");
}
void input_irq(u8 irq,u64 now){
    // Bounded drain, no allocation, IPC, scheduling or rendering in IRQ context.
    for(u32 i=0;i<32;++i){
        const u8 status=arch::in_byte(0x64);
        if((status&1)==0){break;}
        const u8 value=arch::in_byte(0x60);
        if((status&0xc0)!=0){packet_index=0;extended=false;continue;}
        if((status&0x20)!=0){mouse(value,now);}else{keyboard(value,now);}
    }
    arch::pic_eoi(irq);
}
}
