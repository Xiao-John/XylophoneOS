#pragma once
#include <xos/platform.hpp>

// Small fixed-buffer formatters for early diagnostics. No heap, no libc.
namespace xos::format {
inline void text(const char* value) {
    (void)platform::debug_write(value);
}

inline void hex(u64 value) {
    char buffer[19];
    buffer[0] = '0';
    buffer[1] = 'x';
    for (u32 i = 0; i < 16; ++i) {
        const u32 nibble = static_cast<u32>((value >> (60 - 4 * i)) & 0xf);
        buffer[2 + i] = static_cast<char>(nibble < 10 ? '0' + nibble : 'a' + (nibble - 10));
    }
    buffer[18] = '\0';
    text(buffer);
}

inline void decimal(u64 value) {
    char buffer[21];
    u32 index = 20;
    buffer[index] = '\0';
    do {
        buffer[--index] = static_cast<char>('0' + (value % 10));
        value /= 10;
    } while (value != 0);
    text(&buffer[index]);
}
}
