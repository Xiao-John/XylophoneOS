// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; network IRQ additions 2026-10-29 are Apache-2.0.
#include <xos/fault.hpp>
#include <xos/format.hpp>
#include <xos/platform.hpp>
#include <xos/task.hpp>
#include "frame.hpp"
#include "interrupt_entry.hpp"

namespace xos::arch {
extern "C" {
extern const u64 exception_stub_table[32];
extern u8 kernel_stack_top[];
extern void irq0_stub();
extern void irq1_stub();
extern void irq12_stub();
extern void irq5_stub();
extern void irq9_stub();
extern void irq10_stub();
extern void irq11_stub();
extern void syscall_stub();
void gdt_load(const void* pointer);

extern "C" void* interrupt_dispatch(void* frame);
}

namespace {
struct [[gnu::packed]] gdt_entry {
    u16 limit_low;
    u16 base_low;
    u8 base_middle;
    u8 access;
    u8 granularity;
    u8 base_high;
};

struct [[gnu::packed]] tss_entry {
    u16 limit_low;
    u16 base_low;
    u8 base_middle;
    u8 access;
    u8 granularity;
    u8 base_high;
    u32 base_upper;
    u32 reserved;
};

struct [[gnu::packed, gnu::aligned(16)]] task_state_segment {
    u32 reserved0;
    u64 rsp0;
    u64 rsp1;
    u64 rsp2;
    u64 reserved1;
    u64 ist[7];
    u64 reserved2;
    u16 reserved3;
    u16 io_map_base;
};

struct [[gnu::packed]] gdt_table {
    gdt_entry null;
    gdt_entry code;
    gdt_entry data;
    tss_entry tss;
    gdt_entry user_code;
    gdt_entry user_data;
};

struct [[gnu::packed]] idt_entry {
    u16 offset_low;
    u16 selector;
    u8 ist;
    u8 type_attributes;
    u16 offset_middle;
    u32 offset_high;
    u32 zero;
};

struct [[gnu::packed]] descriptor_pointer {
    u16 limit;
    u64 base;
};

alignas(16) gdt_table gdt;
alignas(16) task_state_segment tss;
alignas(16) idt_entry idt[256];
descriptor_pointer gdt_pointer;
descriptor_pointer idt_pointer;
alignas(16) u8 double_fault_stack[8192];
alignas(16) u8 nmi_stack[4096];

void fill_code_entry(gdt_entry& entry, u8 access) {
    entry.limit_low = 0;
    entry.base_low = 0;
    entry.base_middle = 0;
    entry.access = access;
    entry.granularity = 0x20;
    entry.base_high = 0;
}

void fill_data_entry(gdt_entry& entry, u8 access, bool flat) {
    entry.limit_low = 0xffff;
    entry.base_low = 0;
    entry.base_middle = 0;
    entry.access = access;
    entry.granularity = flat ? 0xcf : 0xcf;
    entry.base_high = 0;
}

void fill_tss_entry(tss_entry& entry, u64 base) {
    const u64 limit = sizeof(task_state_segment) - 1;
    entry.limit_low = static_cast<u16>(limit & 0xffff);
    entry.base_low = static_cast<u16>(base & 0xffff);
    entry.base_middle = static_cast<u8>((base >> 16) & 0xff);
    entry.access = 0x89;
    entry.granularity = static_cast<u8>((limit >> 16) & 0x0f);
    entry.base_high = static_cast<u8>((base >> 24) & 0xff);
    entry.base_upper = static_cast<u32>(base >> 32);
    entry.reserved = 0;
}

void fill_gate(idt_entry& gate, u64 offset, u8 selector, u8 ist, u8 attributes) {
    gate.offset_low = static_cast<u16>(offset & 0xffff);
    gate.selector = selector;
    gate.ist = ist;
    gate.type_attributes = attributes;
    gate.offset_middle = static_cast<u16>((offset >> 16) & 0xffff);
    gate.offset_high = static_cast<u32>(offset >> 32);
    gate.zero = 0;
}

u64 read_cr2() {
    u64 value;
    __asm__ volatile("mov %%cr2, %0" : "=r"(value));
    return value;
}
}

void exceptions_init() {
    gdt = gdt_table{};
    tss = task_state_segment{};
    fill_code_entry(gdt.code, 0x9a);
    fill_data_entry(gdt.data, 0x92, true);
    fill_code_entry(gdt.user_code, 0xfa);
    fill_data_entry(gdt.user_data, 0xf2, true);
    tss.rsp0 = reinterpret_cast<u64>(kernel_stack_top);
    tss.ist[0] = reinterpret_cast<u64>(double_fault_stack) + sizeof(double_fault_stack);
    tss.ist[1] = reinterpret_cast<u64>(nmi_stack) + sizeof(nmi_stack);
    tss.io_map_base = static_cast<u16>(sizeof(task_state_segment));
    fill_tss_entry(gdt.tss, reinterpret_cast<u64>(&tss));

    gdt_pointer.limit = static_cast<u16>(sizeof(gdt_table) - 1);
    gdt_pointer.base = reinterpret_cast<u64>(&gdt);
    gdt_load(&gdt_pointer);
    const u16 tss_selector = 0x18;
    __asm__ volatile("ltr %w0" : : "r"(tss_selector));

    for (u32 vector = 0; vector < 256; ++vector) {
        idt[vector] = idt_entry{};
    }
    for (u32 vector = 0; vector < 32; ++vector) {
        const u64 offset = exception_stub_table[vector];
        fill_gate(idt[vector], offset, 0x08,
                  static_cast<u8>(vector == 8 ? 1 : (vector == 2 ? 2 : 0)), 0x8e);
    }
    fill_gate(idt[32], reinterpret_cast<u64>(&irq0_stub), 0x08, 0, 0x8e);
    fill_gate(idt[33], reinterpret_cast<u64>(&irq1_stub), 0x08, 0, 0x8e);
    fill_gate(idt[44], reinterpret_cast<u64>(&irq12_stub), 0x08, 0, 0x8e);
    fill_gate(idt[37], reinterpret_cast<u64>(&irq5_stub), 0x08, 0, 0x8e);
    fill_gate(idt[41], reinterpret_cast<u64>(&irq9_stub), 0x08, 0, 0x8e);
    fill_gate(idt[42], reinterpret_cast<u64>(&irq10_stub), 0x08, 0, 0x8e);
    fill_gate(idt[43], reinterpret_cast<u64>(&irq11_stub), 0x08, 0, 0x8e);
    fill_gate(idt[128], reinterpret_cast<u64>(&syscall_stub), 0x08, 0, 0xee);

    idt_pointer.limit = static_cast<u16>(sizeof(idt) - 1);
    idt_pointer.base = reinterpret_cast<u64>(&idt);
    __asm__ volatile("lidt %0" : : "m"(idt_pointer));
}

void set_kernel_stack(u64 top) {
    tss.rsp0 = top;
}

u64 exception_idt_address() {
    return reinterpret_cast<u64>(&idt);
}
}

extern "C" void* interrupt_dispatch(void* raw_frame) {
    auto* frame = static_cast<xos::arch::interrupt_frame*>(raw_frame);
    const xos::u32 vector = static_cast<xos::u32>(frame->vector);
    if (vector == 128) { return xos::arch::syscall_entry(frame); }
    if (vector == 32) { return xos::arch::timer_entry(frame); }
    if (vector == 33 || vector == 44) { return xos::arch::input_entry(frame); }
    if (vector == 37 || (vector >= 41 && vector <= 43)) {
        xos::platform::device_irq(static_cast<xos::u8>(vector - 32));
        return frame;
    }
    if (vector < 32) {
        if ((frame->cs & 3) == 3) { return xos::arch::user_fault(frame); }
        xos::fault_info info{};
        info.vector = vector;
        info.error = frame->error;
        info.rip = frame->rip;
        info.cs = frame->cs;
        info.rflags = frame->rflags;
        info.has_cr2 = vector == 14;
        info.cr2 = info.has_cr2 ? xos::arch::read_cr2() : 0;
        xos::panic(info);
    }
    return frame;
}

namespace xos {
[[noreturn]] void trigger_fault(fault_trigger kind) {
    switch (kind) {
    case fault_trigger::divide_error:
        __asm__ volatile("xor %%edx, %%edx\n\txor %%ecx, %%ecx\n\t"
                         "mov $1, %%eax\n\tdiv %%ecx"
                         : : : "eax", "ecx", "edx");
        break;
    case fault_trigger::invalid_opcode:
        __asm__ volatile("ud2");
        break;
    case fault_trigger::page_fault: {
        volatile u64* address = reinterpret_cast<volatile u64*>(static_cast<u64>(0xdead0000));
        (void)*address;
        break;
    }
    case fault_trigger::general_protection:
        __asm__ volatile("int $0x30");
        break;
    case fault_trigger::double_fault:
        __asm__ volatile("mov %0, %%rsp\n\tud2"
                         : : "r"(static_cast<u64>(0xdead0000)) : "memory");
        break;
    }
    __builtin_unreachable();
}
}
