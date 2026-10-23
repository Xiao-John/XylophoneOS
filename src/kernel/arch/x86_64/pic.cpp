#include "pic.hpp"
#include "io.hpp"

namespace xos::arch {
namespace {
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

void timer_init(u32 hz) {
    const u32 divisor = pit_frequency / hz;
    out_byte(pit_command, 0x36); // channel 0, lobyte/hibyte, mode 3
    out_byte(pit_channel0, static_cast<u8>(divisor & 0xff));
    out_byte(pit_channel0, static_cast<u8>((divisor >> 8) & 0xff));
}

void pic_eoi(u8 irq) {
    if (irq >= 8) { out_byte(slave_command, 0x20); }
    out_byte(master_command, 0x20);
}
}
