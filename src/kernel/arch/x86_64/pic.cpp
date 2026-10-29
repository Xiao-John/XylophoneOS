// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; network IRQ additions 2026-10-29 are Apache-2.0.
#include "pic.hpp"
#include "io.hpp"

namespace xos::arch {
namespace {
volatile u64 ticks;
constexpr u16 master_command = 0x20;
constexpr u16 master_data = 0x21;
constexpr u16 slave_command = 0xa0;
constexpr u16 slave_data = 0xa1;
constexpr u16 pit_command = 0x43;
constexpr u16 pit_channel0 = 0x40;
constexpr u32 pit_frequency = 1193182;

void io_wait() {
    out_byte(0x80, 0);
}
}

void pic_init() {
    out_byte(master_command, 0x11);
    io_wait();
    out_byte(slave_command, 0x11);
    io_wait();
    out_byte(master_data, 0x20);
    io_wait();
    out_byte(slave_data, 0x28);
    io_wait();
    out_byte(master_data, 0x04);
    io_wait();
    out_byte(slave_data, 0x02);
    io_wait();
    out_byte(master_data, 0x01);
    io_wait();
    out_byte(slave_data, 0x01);
    io_wait();
    out_byte(master_data, 0xfe); // only IRQ0 (PIT) is unmasked
    out_byte(slave_data, 0xff);
}

void pic_input_enable() {
    out_byte(master_data, 0xf8); // PIT, keyboard and slave cascade
    out_byte(slave_data, 0xef); // IRQ12
}

void timer_init(u32 hz) {
    const u32 divisor = pit_frequency / hz;
    out_byte(pit_command, 0x36); // channel 0, lobyte/hibyte, mode 3
    out_byte(pit_channel0, static_cast<u8>(divisor & 0xff));
    out_byte(pit_channel0, static_cast<u8>((divisor >> 8) & 0xff));
}

u64 pic_ticks() { return ticks; }

void pic_line_enable(u8 irq, bool enabled) {
    if (irq >= 16) { return; }
    const u16 port = irq < 8 ? master_data : slave_data;
    const u8 bit = static_cast<u8>(1u << (irq & 7));
    const u8 old = in_byte(port);
    out_byte(port, enabled ? static_cast<u8>(old & ~bit) : static_cast<u8>(old | bit));
    if (enabled && irq >= 8) { out_byte(master_data, static_cast<u8>(in_byte(master_data) & ~4u)); }
}

void pic_eoi(u8 irq) {
    if (irq == 0) { ticks = ticks + 1; }
    if (irq >= 8) { out_byte(slave_command, 0x20); }
    out_byte(master_command, 0x20);
}
}
