// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "named_resource_data.hpp"
#include "user_login.hpp"

namespace xos::user::pumpkin::named_operator {
inline constexpr u32 magic = 0x314e4b50; // PKN1
inline constexpr u16 version = 2;
inline constexpr u8 conflict = 4;
inline constexpr u8 source_rejected = 5;
enum class operation : u8 { select = 1, put, erase, import_fat };

struct packet {
    u32 tag = magic;
    u16 format = version;
    operation op{};
    u8 result = 0;
    u64 sequence = 1;
    named_resource_request fields{};
    u8 payload[96]{};
};
static_assert(sizeof(packet) == sizeof(anchor_guest::packet));

inline bool header(const packet& value, operation op, u64 sequence) {
    return value.tag == magic && value.format == version && value.op == op && value.sequence == sequence;
}

inline operation for_scenario(anchor_guest::scenario mode) {
    switch (mode) {
    case anchor_guest::scenario::user_named_read: return operation::select;
    case anchor_guest::scenario::user_named_put: return operation::put;
    case anchor_guest::scenario::user_named_erase: return operation::erase;
    case anchor_guest::scenario::user_named_import: return operation::import_fat;
    default: return {};
    }
}

inline bool empty(const packet& value) {
    return !has_bytes(reinterpret_cast<const u8*>(&value.fields), sizeof(value.fields)) &&
        !has_bytes(value.payload, sizeof(value.payload));
}

inline bool selection(const packet& value, operation op) {
    if (!header(value, op, 1) || value.result ||
        !valid_named_request(value.fields, op == operation::put || op == operation::import_fat) ||
        (op == operation::erase && !value.fields.generation)) { return false; }
    if (op != operation::import_fat) { return !has_bytes(value.payload, sizeof(value.payload)); }
    const auto length = value.fields.data;
    if (length < 2 || length >= sizeof(value.payload) || value.payload[0] != '/' ||
        has_bytes(value.payload + length, sizeof(value.payload) - length)) { return false; }
    for (u32 index = 0; index < length; ++index) {
        if (value.payload[index] < 32 || value.payload[index] == 127 || value.payload[index] == '\\') { return false; }
    }
    return true;
}

inline bool outcome(const packet& value, const packet& selected) {
    if (!header(value, selected.op, 2)) { return false; }
    if (value.result != 1) {
        const auto denied = value.result == user_login::denied || value.result == user_login::resource_denied;
        return empty(value) && (selected.op == operation::select ? denied : value.result == conflict ||
            (selected.op == operation::import_fat && value.result == source_rejected));
    }
    const auto& result = value.fields;
    const auto& requested = selected.fields;
    if (!valid_named_request(result, selected.op == operation::select) || !result.generation ||
        result.length != requested.length || __builtin_memcmp(result.name, requested.name, result.length) != 0) {
        return false;
    }
    if (selected.op == operation::select) {
        if (!result.data || result.data > named_resource_bytes ||
            has_bytes(value.payload + result.data, sizeof(value.payload) - result.data)) { return false; }
    } else if (has_bytes(value.payload, sizeof(value.payload))) { return false; }
    return selected.op == operation::put || selected.op == operation::import_fat ?
        result.generation > requested.generation :
        !requested.generation || result.generation == requested.generation;
}
}
