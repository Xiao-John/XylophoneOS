// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>
namespace xos {
inline constexpr u64 sys_display = 63, sys_display_present = 64;
inline constexpr i64 display_denied=-1, display_invalid=-2, display_again=-3,
    display_resources=-5, display_unavailable=-19, display_fault=-14, display_busy=-16;
inline constexpr u32 display_xrgb8888=1, display_event_capacity=64;
struct display_mode { u32 version, size, width, height, stride, format; u64 bytes; };
struct display_rect { u32 x,y,width,height; };
struct display_present { u32 version,size; u64 pixels,length; u32 stride,format; display_rect rect; };
struct display_channel { u32 request,response; u64 pid; };
struct display_event {
    u64 sequence, monotonic_ns;
    u32 kind, code, modifiers, buttons;
    i32 dx,dy,x,y;
    u32 lost,reserved;
};
enum class display_action : u64 { mode, grant_service, connect, accept, wait,
    disconnect, input, focus, shutdown, service_info };
enum class display_operation : u32 { mode=1, present, input, focus, close, stop };
struct display_request { u32 version,size; display_operation operation; u32 reserved; display_present present; };
struct display_reply { i64 result; display_mode mode; display_event event; };
static_assert(sizeof(display_mode)==32 && sizeof(display_present)==48);
static_assert(sizeof(display_event)==56 && sizeof(display_request)==64 && sizeof(display_reply)==96);
}
