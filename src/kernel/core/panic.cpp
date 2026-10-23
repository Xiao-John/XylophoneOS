#include <xos/fault.hpp>
#include <xos/format.hpp>
#include <xos/platform.hpp>

namespace xos {
namespace {
constexpr const char* vector_names[32] = {
    "divide_error", "debug", "non_maskable_interrupt", "breakpoint",
    "overflow", "bound_range", "invalid_opcode", "device_not_available",
    "double_fault", "coprocessor_segment_overrun", "invalid_tss",
    "segment_not_present", "stack_segment_fault", "general_protection",
    "page_fault", "reserved", "x87_floating_point", "alignment_check",
    "machine_check", "simd_floating_point", "virtualization",
    "control_protection", "reserved", "reserved", "reserved", "reserved",
    "reserved", "reserved", "reserved", "reserved", "reserved", "reserved",
};
}

[[noreturn]] void panic(const fault_info& info) {
    format::text("[panic] vector=");
    format::decimal(info.vector);
    format::text(" ");
    format::text(info.vector < 32 ? vector_names[info.vector] : "reserved");
    format::text(" error=");
    format::hex(info.error);
    format::text("\r\n[panic] rip=");
    format::hex(info.rip);
    format::text(" cs=");
    format::hex(info.cs);
    format::text(" rflags=");
    format::hex(info.rflags);
    format::text("\r\n");
    if (info.has_cr2) {
        format::text("[panic] cr2=");
        format::hex(info.cr2);
        format::text("\r\n");
    }
    format::text("[panic] result=halt\r\n");
    arch::halt();
}
}
