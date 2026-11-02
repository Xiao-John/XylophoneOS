// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>
#include <xos/unicode_width_data.hpp>

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

// Match newlib wcwidth in the ordinary UTF-8 width mode for valid printable
// scalars. The interactive channel rejects C0/C1 controls separately.
template <u32 N>
inline bool width_contains(u32 codepoint, const width_data::interval (&table)[N]) {
    u32 first = 0, last = N;
    while (first < last) {
        const u32 middle = first + (last - first) / 2;
        if (codepoint < table[middle].first) { last = middle; }
        else if (codepoint > table[middle].last) { first = middle + 1; }
        else { return true; }
    }
    return false;
}

inline u32 width(u32 codepoint) {
    if (codepoint == 0) { return 0; }
    if (width_contains(codepoint, width_data::combining)) { return 0; }
    if (width_contains(codepoint, width_data::wide)) { return 2; }
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
