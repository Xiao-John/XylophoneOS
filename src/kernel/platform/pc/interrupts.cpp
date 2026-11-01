// SPDX-License-Identifier: Apache-2.0
// PC PIC/PIT initialization and pure interrupt acknowledgment.
#include "interrupts.hpp"
#include "arch/x86_64/io.hpp"
#include <xos/clock.hpp>
#include <xos/platform.hpp>

namespace xos::platform::pc {
namespace {
using arch::in_byte;
using arch::out_byte;
constexpr u16 master_command = 0x20, master_data = 0x21;
constexpr u16 slave_command = 0xa0, slave_data = 0xa1;
bool initialized;

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
}
