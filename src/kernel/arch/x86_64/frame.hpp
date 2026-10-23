#pragma once
#include <xos/types.hpp>

namespace xos::arch {
// Layout must match interrupt_common's push order. rsp/ss are only meaningful
// when the interrupted context was ring3; the CPU pushes them on privilege change.
struct [[gnu::packed]] interrupt_frame {
    u64 r15;
    u64 r14;
    u64 r13;
    u64 r12;
    u64 r11;
    u64 r10;
    u64 r9;
    u64 r8;
    u64 rbp;
    u64 rdi;
    u64 rsi;
    u64 rdx;
    u64 rcx;
    u64 rbx;
    u64 rax;
    u64 vector;
    u64 error;
    u64 rip;
    u64 cs;
    u64 rflags;
    u64 rsp;
    u64 ss;
};
static_assert(sizeof(interrupt_frame) == 22 * 8);
}
