#pragma once
#include "frame.hpp"

namespace xos::arch {
void* timer_entry(interrupt_frame* frame);
void* syscall_entry(interrupt_frame* frame);
void* user_fault(interrupt_frame* frame);
}
