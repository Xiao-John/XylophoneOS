// SPDX-License-Identifier: Apache-2.0
#include <xos/display_client.hpp>
namespace {
using namespace xos;using namespace xos::sdk;
u32 pixels[800*600];
display_mode screen{};
display_client client;
void rectangle(u32 x,u32 y,u32 width,u32 height,u32 color){
    for(u32 row=y;row<y+height;++row){for(u32 col=x;col<x+width;++col){pixels[row*screen.width+col]=color;}}
}
display_present buffer(display_rect rect){
    return {1,sizeof(display_present),reinterpret_cast<u64>(pixels),u64{screen.width}*screen.height*4,
        screen.width*4,display_xrgb8888,rect};
}
bool expect(bool condition,const char* label){
    print("[gfx-check] ");print(label);print(condition?"=pass\n":"=FAIL\n");return condition;
}
void event_line(const display_event& e){
    print("[gfx-event] seq=");decimal(e.sequence);print(" ns=");decimal(e.monotonic_ns);
    print(" kind=");decimal(e.kind);print(" code=");decimal(e.code);print(" mods=");decimal(e.modifiers);
    print(" buttons=");decimal(e.buttons);print(" dx=");signed_decimal(e.dx);print(" dy=");signed_decimal(e.dy);
    print(" x=");signed_decimal(e.x);print(" y=");signed_decimal(e.y);print(" lost=");decimal(e.lost);print("\n");
}
}
extern "C" int xos_user_main(const xos::startup_info* startup){
    using namespace xos;using namespace xos::sdk;
    const auto* argv=reinterpret_cast<const char* const*>(startup->argv);
    const char* action=startup->argc>1?argv[1]:"hold";
    if(equal(action,"deny")){
        display_event event{};
        bool ok=expect(display_control(display_action::grant_service,pid())==display_denied,"grant_denied");
        ok&=expect(syscall(sys_display_present,1)==display_denied,"direct_present_denied");
        ok&=expect(display_control(display_action::input,reinterpret_cast<u64>(&event))==display_denied,"input_denied");
        ok&=expect(display_control(display_action::focus,pid())==display_denied,"focus_denied");
        return ok?0:1;
    }
    const i64 opened=client.open();
    if(opened!=0){print("[gfx] open=");signed_decimal(opened);print("\n");return 1;}
    if(equal(action,"fault")){print("[gfx] fault_after_connect\n");__asm__ volatile("ud2");}
    if(equal(action,"stop")){
        const auto result=client.stop();(void)client.close();return result==0?0:1;
    }
    if(client.mode(screen)!=0){(void)client.close();return 2;}
    print("[gfx] width=");decimal(screen.width);print(" height=");decimal(screen.height);
    print(" stride=");decimal(screen.stride);print(" format=");decimal(screen.format);print("\n");
    rectangle(0,0,screen.width,screen.height,0x102030);
    const u32 colors[]={0xe74c3c,0xf39c12,0xf1c40f,0x2ecc71,0x1abc9c,0x3498db,0x9b59b6,0xec70a6};
    for(u32 i=0;i<8;++i){rectangle(40+i*70,120,56,240-i*12,colors[i]);}
    auto frame=buffer({0,0,screen.width,screen.height});
    if(client.present(frame)!=0){(void)client.close();return 3;}
    rectangle(4,4,12,12,0xabcdef);
    if(client.present(buffer({4,4,12,12}))!=0){(void)client.close();return 4;}
    if(equal(action,"check")){
        bool ok=expect(screen.version==1 && screen.size==32 && screen.width==800 && screen.height==600 &&
            screen.stride==3200 && screen.format==1 && screen.bytes==1920000,"mode");
        auto invalid=frame;invalid.rect={799,0,2,1};
        ok&=expect(client.present(invalid)==display_invalid,"rectangle_oob");
        invalid=frame;invalid.rect.width=0;
        ok&=expect(client.present(invalid)==display_invalid,"empty_rectangle");
        invalid=frame;invalid.stride=0xffffffff;
        ok&=expect(client.present(invalid)==display_invalid,"stride_overflow");
        invalid=frame;invalid.length=~u64{0};
        ok&=expect(client.present(invalid)==display_invalid,"length_overflow");
        invalid=frame;invalid.length-=4;
        ok&=expect(client.present(invalid)==display_invalid,"short_length");
        invalid=frame;invalid.format=99;
        ok&=expect(client.present(invalid)==display_invalid,"bad_format");
        invalid=frame;invalid.version=2;
        ok&=expect(client.present(invalid)==display_invalid,"bad_version");
        invalid=frame;invalid.pixels=0x30000000;
        ok&=expect(client.present(invalid)==display_fault,"kernel_buffer");
        invalid=frame;invalid.pixels=0x7ffff000;
        ok&=expect(client.present(invalid)==display_fault,"pointer_end_overflow");
        invalid=frame;invalid.pixels=process_heap_begin;
        ok&=expect(client.present(invalid)==display_fault,"unmapped_buffer");
        const i64 original=syscall(sys_heap_break);
        ok&=expect(syscall(sys_heap_break,process_heap_end)==process_error_resources,"page_quota");
        ok&=expect(syscall(sys_heap_break)==original,"quota_rollback");
        ok&=expect(client.focus(false)==0,"focus_off");
        display_event event{};
        ok&=expect(client.input(event)==display_denied,"unfocused_input_denied");
        ok&=expect(client.present(frame)==display_denied,"unfocused_present_denied");
        ok&=expect(client.focus(true)==0,"focus_restore");
        ok&=expect(client.input(event)==display_again,"state_reset");
        ok&=expect(client.close()==0,"close");
        print(ok?"[gfx] checks=pass\n":"[gfx] checks=FAIL\n");return ok?0:5;
    }
    print("[gfx] ready input=ps2 exit=escape_or_q\n");
    if(equal(action,"overflow")){
        const u64 end=ticks()+200;while(ticks()<end){yield();}
        print("[gfx] overflow_drain\n");
    }
    for(;;){
        display_event event{};
        const auto result=client.input(event);
        if(result==display_again){if(client.wait_input()!=0){break;}continue;}
        if(result!=0){print("[gfx] input_error=");signed_decimal(result);print("\n");break;}
        event_line(event);
        if(event.kind==1 && (event.code==1 || event.code==0x10)){break;}
        const u32 color=event.kind==3?(event.buttons!=0?0xffffff:0x00ffff):0xff00ff;
        rectangle(0,0,screen.width,32,0x102030);
        const u32 marker=event.kind==3?static_cast<u32>(event.x):event.code%screen.width;
        rectangle(marker<screen.width-8?marker:screen.width-8,8,8,16,color);
        (void)client.present(buffer({0,0,screen.width,32}));
    }
    (void)client.close();print("[gfx] closed terminal=serial\n");return 0;
}
