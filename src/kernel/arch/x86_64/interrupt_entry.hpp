#pragma once
#include "frame.hpp"

namespace xos::arch {
// Called with interrupts disabled before returning to a user context. A zero
// length denies all ports; invalid ranges also leave the bitmap deny-all.
bool set_user_io_window(u32 first, u32 length);
void* input_entry(interrupt_frame* frame);
void* timer_entry(interrupt_frame* frame);
void* syscall_entry(interrupt_frame* frame);
void* user_fault(interrupt_frame* frame);
}
