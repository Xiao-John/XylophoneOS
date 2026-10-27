// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/sdk.hpp>
#include <xos/display_abi.hpp>
namespace xos::sdk {
inline i64 display_control(display_action action,u64 value=0,u64 extra=0){
    return syscall(sys_display,static_cast<u64>(action),value,extra);
}
// One synchronous transaction per channel. Threaded callers serialize this
// object with their SDK mutex. Kernel returns FULL for concurrent requests.
class display_client {
    display_channel channel{};
public:
    i64 open(){return display_control(display_action::connect,reinterpret_cast<u64>(&channel));}
    i64 close(){const auto result=display_control(display_action::disconnect);channel={};return result;}
    i64 call(display_request request,display_reply& reply){
        request.version=1;request.size=sizeof(request);
        i64 result=ipc_send(channel.request,&request,sizeof(request));
        if(result!=0){return result;}
        result=display_control(display_action::wait,channel.response);
        if(result!=0){return result;}
        result=ipc_recv(channel.response,&reply,sizeof(reply));
        return result==sizeof(reply)?reply.result:result;
    }
    i64 mode(display_mode& mode){
        display_reply reply{};display_request request{};request.operation=display_operation::mode;
        const auto result=call(request,reply);if(result==0){mode=reply.mode;}return result;
    }
    i64 present(display_present buffer){
        display_reply reply{};display_request request{};request.operation=display_operation::present;request.present=buffer;
        return call(request,reply);
    }
    i64 input(display_event& event){
        display_reply reply{};display_request request{};request.operation=display_operation::input;
        const auto result=call(request,reply);if(result==0){event=reply.event;}return result;
    }
    i64 focus(bool active){
        display_reply reply{};display_request request{};request.operation=display_operation::focus;
        request.present.pixels=active?1u:0u;return call(request,reply);
    }
    i64 stop(){display_reply reply{};display_request request{};request.operation=display_operation::stop;return call(request,reply);}
    i64 wait_input(){return display_control(display_action::wait);}
};
}
