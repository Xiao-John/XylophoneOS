#include <xos/platform.hpp>
#include "arch/x86_64/io.hpp"

namespace xos::platform {
namespace {
constexpr u16 uart = 0x3f8;
usize row;
usize column;
int pending_input = -1;
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
    if (pending_input < 0 && (arch::in_byte(uart + 5) & 1) != 0) {
        pending_input = static_cast<int>(arch::in_byte(uart));
    }
    return pending_input;
}
int debug_read() {
    const int value = debug_peek();
    pending_input = -1;
    return value;
}

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
            if ((arch::in_byte(uart + 5) & 0x20) != 0) { ready = true; break; }
        }
        if (ready) { arch::out_byte(uart, static_cast<u8>(value)); }
        else { return static_cast<i64>(sent); }
        vga_char(value);
    }
    return static_cast<i64>(sent);
}
}
