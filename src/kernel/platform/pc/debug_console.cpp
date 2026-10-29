#include <xos/platform.hpp>
#include <xos/byte_queue.hpp>
#include "arch/x86_64/io.hpp"

namespace xos::platform {
namespace {
constexpr u16 uart = 0x3f8;
usize row;
usize column;
byte_queue<1024> input_queue;
bool input_irq_enabled;
u64 input_overruns;
bool graphics_active;
auto* const text_buffer = reinterpret_cast<volatile u16*>(0xb8000);
void vga_char(char value) {
    if (graphics_active) { return; }
    if (value == '\r') { column = 0; return; }
    if (value == '\n') { ++row; column = 0; }
    else {
        text_buffer[row * 80 + column] = static_cast<u16>(0x0700 | static_cast<u8>(value));
        if (++column == 80) { column = 0; ++row; }
    }
    if (row == 25) {
        for (usize i = 0; i < 24 * 80; ++i) { text_buffer[i] = text_buffer[i + 80]; }
        for (usize i = 24 * 80; i < 25 * 80; ++i) { text_buffer[i] = 0x0720; }
        row = 24;
    }
}
u8 debug_input_status() {
    const u8 status = arch::in_byte(uart + 5);
    // Reading the line-status register clears the UART overrun indication.
    if ((status & 0x02) != 0 && input_overruns != ~u64{0}) { ++input_overruns; }
    return status;
}
}
void debug_graphics(bool active) { graphics_active = active; }
void debug_init() {
    arch::out_byte(uart + 1, 0);
    arch::out_byte(uart + 3, 0x80);
    arch::out_byte(uart, 1);
    arch::out_byte(uart + 1, 0);
    arch::out_byte(uart + 3, 3);
    arch::out_byte(uart + 2, 0xc7);
    arch::out_byte(uart + 4, 0x0b);
    row = 0;
    column = 0;
    if (!graphics_active) {
        for (usize i = 0; i < 80 * 25; ++i) { text_buffer[i] = 0x0720; }
    }
}
int debug_peek() {
    if (!input_irq_enabled && input_queue.length() == 0 && (debug_input_status() & 1) != 0) {
        (void)input_queue.push(arch::in_byte(uart));
    }
    u8 value = 0;
    return input_queue.peek(value) ? static_cast<int>(value) : -1;
}
int debug_read() {
    const int value = debug_peek();
    u8 ignored = 0;
    if (value >= 0) { (void)input_queue.pop(ignored); }
    return value;
}

void debug_input_enable() {
    input_irq_enabled = true;
    arch::out_byte(uart + 1, 1); // receive data available
}

void debug_input_irq() {
    // Bound work per interrupt; UART FIFO remains asserted if more input arrives.
    for (u32 i = 0; i < 64 && (debug_input_status() & 1) != 0; ++i) {
        (void)input_queue.push(arch::in_byte(uart));
    }
}

u64 debug_input_dropped() { return input_queue.dropped(); }
u64 debug_input_overruns() { return input_overruns; }

bool debug_write(const char* text) {
    usize length = 0;
    while (text[length] != '\0') { ++length; }
    return debug_write_bytes(reinterpret_cast<const u8*>(text), length) == static_cast<i64>(length);
}
i64 debug_write_bytes(const u8* bytes, usize length) {
    usize sent = 0;
    for (; sent < length; ++sent) {
        const char value = static_cast<char>(bytes[sent]);
        bool ready = false;
        for (u32 wait = 0; wait < 65535; ++wait) {
            if ((debug_input_status() & 0x20) != 0) { ready = true; break; }
        }
        if (ready) { arch::out_byte(uart, static_cast<u8>(value)); }
        else { return static_cast<i64>(sent); }
        vga_char(value);
    }
    return static_cast<i64>(sent);
}
}
