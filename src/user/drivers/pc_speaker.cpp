// SPDX-License-Identifier: Apache-2.0
#include "pc_speaker.hpp"

namespace xos::user::pc_speaker {
namespace {
constexpr u32 pit_input_hz = 1193182;
u8 read_port(u16 port) {
    u8 result;
    __asm__ volatile("inb %1, %0" : "=a"(result) : "Nd"(port));
    return result;
}
void write_port(u16 port, u8 value) {
    __asm__ volatile("outb %0, %1" : : "a"(value), "Nd"(port));
}
}
i64 play(u32 frequency_hz) {
    if (frequency_hz < audio::min_frequency_hz || frequency_hz > audio::max_frequency_hz)
        return process_error_invalid;
    const u32 divisor = (pit_input_hz + frequency_hz / 2) / frequency_hz;
    if (divisor == 0 || divisor > 0xffff) return process_error_invalid;
    // Channel 2, low/high divisor, mode 3, binary counting.
    write_port(0x43, 0xb6);
    write_port(0x42, static_cast<u8>(divisor));
    write_port(0x42, static_cast<u8>(divisor >> 8));
    // Preserve refresh and other board-specific bits at 0x61.
    write_port(0x61, static_cast<u8>(read_port(0x61) | 0x03));
    return 0;
}
}
