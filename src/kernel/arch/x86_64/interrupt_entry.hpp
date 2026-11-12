#pragma once
#include "frame.hpp"

namespace xos::arch {
// Called with interrupts disabled before returning to a user context. A zero
// length denies all ports; invalid ranges also leave the bitmap deny-all.
bool set_user_io_permissions(u32 first, u32 length, bool pc_speaker);
void cpu_interrupt_enter(interrupt_frame* frame);
void cpu_interrupt_leave(interrupt_frame* frame);
void* input_entry(interrupt_frame* frame);
void* timer_entry(interrupt_frame* frame);
void* syscall_entry(interrupt_frame* frame);
void* user_fault(interrupt_frame* frame);
}
