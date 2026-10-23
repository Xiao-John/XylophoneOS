#pragma once
#include <xos/types.hpp>

namespace xos {
struct fault_info {
    u32 vector;
    u64 error;
    bool has_cr2;
    u64 rip;
    u64 cs;
    u64 rflags;
    u64 cr2;
};

[[noreturn]] void panic(const fault_info& info);

enum class fault_trigger : u8 { divide_error, invalid_opcode, page_fault,
                                general_protection, double_fault };
[[noreturn]] void trigger_fault(fault_trigger kind);
}

namespace xos::arch {
void exceptions_init();
u64 exception_idt_address();
}
