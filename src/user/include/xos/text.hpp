// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>

// Byte-oriented UTF-8 helpers for the interactive text channel. This is not a
// locale implementation: it validates and decodes UTF-8 so line editors can
// delete whole code points and erase the right number of terminal columns.
namespace xos::text {
enum class decode_status { ok, incomplete, invalid };

struct decoded {
    u32 codepoint;
    u32 bytes;
};

inline bool continuation(u8 value) { return (value & 0xc0) == 0x80; }

inline decode_status decode(const char* data, u32 length, decoded& out) {
    if (length == 0) { return decode_status::incomplete; }
    const u8 lead = static_cast<u8>(data[0]);
    if (lead < 0x80) {
        out = decoded{lead, 1};
        return decode_status::ok;
    }
    u32 count = 0;
    u32 value = 0;
    u32 minimum = 0;
    if ((lead & 0xe0) == 0xc0) {
        count = 2;
        value = lead & 0x1f;
        minimum = 0x80;
    } else if ((lead & 0xf0) == 0xe0) {
        count = 3;
        value = lead & 0x0f;
        minimum = 0x800;
    } else if ((lead & 0xf8) == 0xf0) {
        count = 4;
        value = lead & 0x07;
        minimum = 0x10000;
    } else {
        return decode_status::invalid;
    }
    if (length < count) {
        for (u32 i = 1; i < length; ++i) {
            if (!continuation(static_cast<u8>(data[i]))) { return decode_status::invalid; }
        }
        return decode_status::incomplete;
    }
    for (u32 i = 1; i < count; ++i) {
        const u8 next = static_cast<u8>(data[i]);
        if (!continuation(next)) { return decode_status::invalid; }
        value = (value << 6) | (next & 0x3f);
    }
    if (value < minimum || value > 0x10ffff || (value >= 0xd800 && value <= 0xdfff)) {
        return decode_status::invalid;
    }
    out = decoded{value, count};
    return decode_status::ok;
}

inline bool valid(const char* data, u32 length) {
    u32 index = 0;
    while (index < length) {
        decoded unit{};
        if (decode(data + index, length - index, unit) != decode_status::ok) { return false; }
        index += unit.bytes;
    }
    return true;
}

inline bool in_range(u32 value, u32 first, u32 last) {
    return value >= first && value <= last;
}

inline u32 width(u32 codepoint) {
    if (in_range(codepoint, 0x0300, 0x036f) || in_range(codepoint, 0x1ab0, 0x1aff) ||
        in_range(codepoint, 0x1dc0, 0x1dff) || in_range(codepoint, 0x20d0, 0x20ff) ||
        in_range(codepoint, 0xfe20, 0xfe2f)) {
        return 0;
    }
    if (in_range(codepoint, 0x1100, 0x115f) || in_range(codepoint, 0x2329, 0x232a) ||
        in_range(codepoint, 0x2e80, 0x303e) || in_range(codepoint, 0x3041, 0x33ff) ||
        in_range(codepoint, 0x3400, 0x4dbf) || in_range(codepoint, 0x4e00, 0x9fff) ||
        in_range(codepoint, 0xa000, 0xa4cf) || in_range(codepoint, 0xa960, 0xa97f) ||
        in_range(codepoint, 0xac00, 0xd7a3) || in_range(codepoint, 0xf900, 0xfaff) ||
        in_range(codepoint, 0xfe10, 0xfe19) || in_range(codepoint, 0xfe30, 0xfe6f) ||
        in_range(codepoint, 0xff00, 0xff60) || in_range(codepoint, 0xffe0, 0xffe6) ||
        in_range(codepoint, 0x1b000, 0x1b2ff) || in_range(codepoint, 0x1f300, 0x1f64f) ||
        in_range(codepoint, 0x1f900, 0x1f9ff) || in_range(codepoint, 0x20000, 0x3fffd)) {
        return 2;
    }
    return 1;
}

struct erase_result {
    u32 size;
    u32 columns;
};

// Drop the last complete code point. A trailing incomplete sequence and any
// trailing invalid bytes are removed without erasing a cell.
inline erase_result erase_last(const char* data, u32 length) {
    u32 index = 0;
    u32 last_start = 0;
    u32 last_width = 1;
    bool any = false;
    while (index < length) {
        decoded unit{};
        const decode_status status = decode(data + index, length - index, unit);
        if (status == decode_status::ok) {
            last_start = index;
            last_width = width(unit.codepoint);
            index += unit.bytes;
            any = true;
        } else if (status == decode_status::incomplete) {
            return erase_result{index, 0};
        } else {
            last_start = index;
            last_width = 1;
            ++index;
            any = true;
        }
    }
    if (!any) { return erase_result{length, 0}; }
    return erase_result{last_start, last_width};
}
}
