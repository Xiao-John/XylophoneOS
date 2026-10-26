// SPDX-License-Identifier: Apache-2.0
#include <xos/display_client.hpp>
extern "C" int xos_user_main(const xos::startup_info*) {
    using namespace xos;using namespace xos::sdk;
    // Supervisor grants the narrowly scoped role immediately after spawn.
    const auto deadline=ticks()+100;
    while(display_control(display_action::service_info)!=static_cast<i64>(pid())){
        if(ticks()>=deadline){print("[display-service] grant=missing\n");return 1;}yield();
    }
    u64 sectors=0;u32 send=0,receive=0;
    if(ipc_handles(send,receive)!=0 || send!=0 || receive!=0 ||
       syscall(sys_block_info,reinterpret_cast<u64>(&sectors))!=block_error_denied ||
       syscall(sys_process_create,7)!=process_error_denied){return 2;}
    print("[display-service] ready file=denied block=denied spawn=denied\n");
    for(;;){
        display_channel channel{};
        const auto accepted=display_control(display_action::accept,reinterpret_cast<u64>(&channel));
        if(accepted!=0){(void)display_control(display_action::wait);continue;}
        display_request request{};
        const auto received=ipc_recv(channel.request,&request,sizeof(request));
        if(received<0){(void)display_control(display_action::wait,channel.request);continue;}
        display_reply reply{};reply.result=display_invalid;
        bool stop=false;
        if(received==sizeof(request) && request.version==1 && request.size==sizeof(request) && request.reserved==0){
            switch(request.operation){
            case display_operation::mode:
                reply.result=display_control(display_action::mode,reinterpret_cast<u64>(&reply.mode));break;
            case display_operation::present:
                reply.result=syscall(sys_display_present,channel.request);break;
            case display_operation::input:
                reply.result=display_control(display_action::input,reinterpret_cast<u64>(&reply.event));break;
            case display_operation::focus:
                reply.result=display_control(display_action::focus,request.present.pixels!=0?channel.pid:0);break;
            case display_operation::close:reply.result=0;break;
            case display_operation::stop:reply.result=0;stop=true;break;
            }
        }
        (void)ipc_send(channel.response,&reply,sizeof(reply));
        if(stop){
            while(display_control(display_action::accept,reinterpret_cast<u64>(&channel))==0){yield();}
            print("[display-service] stopped\n");return 0;
        }
    }
}
