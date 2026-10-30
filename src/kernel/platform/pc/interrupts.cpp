// SPDX-License-Identifier: MIT AND Apache-2.0
// PIC/PIT programming relocated from the historical MIT arch/pic.cpp.
// New platform ownership and exclusive diagnostic routing are Apache-2.0.
#include "interrupts.hpp"
#include "arch/x86_64/io.hpp"
#include <xos/clock.hpp>
#include <xos/platform.hpp>
#include "build_info.hpp"

namespace xos::platform::pc {
namespace {
using arch::in_byte;
using arch::out_byte;
constexpr u16 master_command = 0x20, master_data = 0x21;
constexpr u16 slave_command = 0xa0, slave_data = 0xa1;
bool initialized;
#if XOS_NET_BOOT_DIAGNOSTIC || XOS_CLOCK_IRQ_PROBE
diagnostic_irq_handler diagnostic_handler;
u8 diagnostic_line;
bool original_level, original_cascade_masked;
#endif

void io_wait() { out_byte(0x80, 0); }
void pic_init() {
    out_byte(master_command, 0x11); io_wait();
    out_byte(slave_command, 0x11); io_wait();
    out_byte(master_data, 0x20); io_wait();
    out_byte(slave_data, 0x28); io_wait();
    out_byte(master_data, 0x04); io_wait();
    out_byte(slave_data, 0x02); io_wait();
    out_byte(master_data, 0x01); io_wait();
    out_byte(slave_data, 0x01); io_wait();
    out_byte(master_data, 0xfe); // IRQ0 only, input enabled by its own init later.
    out_byte(slave_data, 0xff);
}
void timer_init() {
    constexpr u32 frequency = 1193182;
    constexpr u32 hz = 1000000000ull / clock::resolution_ns;
    static_assert(hz == 100);
    constexpr u32 divisor = frequency / hz;
    out_byte(0x43, 0x36);
    out_byte(0x40, static_cast<u8>(divisor));
    out_byte(0x40, static_cast<u8>(divisor >> 8));
}
void change_bit(u16 port, u8 bit, bool set) {
    const u8 value = in_byte(port);
    out_byte(port, set ? static_cast<u8>(value | bit) : static_cast<u8>(value & ~bit));
}
}

void pic_eoi(u8 irq) {
    if (irq >= 8) { out_byte(slave_command, 0x20); }
    out_byte(master_command, 0x20);
}
void pic_input_enable() {
    // Preserve unrelated routes instead of overwriting both mask registers.
    change_bit(master_data, 0x06, false);
    change_bit(slave_data, 0x10, false);
}
#if XOS_NET_BOOT_DIAGNOSTIC || XOS_CLOCK_IRQ_PROBE
bool claim_diagnostic_irq(u8 irq, diagnostic_irq_handler handler) {
    if (!initialized || handler == nullptr || diagnostic_handler != nullptr ||
        (irq != 5 && irq != 9 && irq != 10 && irq != 11)) { return false; }
    const u16 mask_port = irq < 8 ? master_data : slave_data;
    const u16 elcr_port = irq < 8 ? 0x4d0 : 0x4d1;
    const u8 bit = static_cast<u8>(1u << (irq & 7));
    if ((in_byte(mask_port) & bit) == 0) { return false; }
    original_level = (in_byte(elcr_port) & bit) != 0;
    original_cascade_masked = (in_byte(master_data) & 4) != 0;
    change_bit(elcr_port, bit, true);
    if ((in_byte(elcr_port) & bit) == 0) {
        change_bit(elcr_port, bit, original_level);
        return false;
    }
    diagnostic_line = irq;
    diagnostic_handler = handler;
    if (irq >= 8) { change_bit(master_data, 4, false); }
    change_bit(mask_port, bit, false);
    return true;
}
bool release_diagnostic_irq(u8 irq, diagnostic_irq_handler handler) {
    if (diagnostic_handler == nullptr || handler != diagnostic_handler || irq != diagnostic_line) { return false; }
    const u8 bit = static_cast<u8>(1u << (irq & 7));
    change_bit(irq < 8 ? master_data : slave_data, bit, true);
    diagnostic_handler = nullptr;
    change_bit(irq < 8 ? 0x4d0 : 0x4d1, bit, original_level);
    if (irq >= 8 && original_cascade_masked && in_byte(slave_data) == 0xff) {
        change_bit(master_data, 4, true);
    }
    return true;
}
#endif
}

namespace xos::platform {
void interrupts_init() {
    if (pc::initialized) { return; }
    // System boot calls this after IDT and task structures exist, with IF=0.
    pc::pic_init();
    pc::timer_init();
    pc::initialized = true;
}
void timer_interrupt() {
    clock::timer_interrupt();
    pc::pic_eoi(0);
}
void device_irq(u8 irq) {
#if XOS_NET_BOOT_DIAGNOSTIC || XOS_CLOCK_IRQ_PROBE
    if (pc::diagnostic_handler != nullptr && irq == pc::diagnostic_line) {
        pc::diagnostic_handler(irq); // Device acknowledges only its own ISR.
    }
#endif
    pc::pic_eoi(irq);
}
}
