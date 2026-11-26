// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "user_login.hpp"

namespace xos::user::pumpkin::named_operator {
inline constexpr u32 magic = 0x314e4b50; // PKN1
inline constexpr u16 version = 1;
inline constexpr u8 conflict = 4;
enum class operation : u8 { select = 1, put, erase };

struct packet {
    u32 tag = magic;
    u16 format = version;
    operation op{};
    u8 result = 0;
    u64 sequence = 1;
    named_resource_request fields{};
    u8 reserved[96]{};
};
static_assert(sizeof(packet) == sizeof(anchor_guest::packet));

inline bool header(const packet& value, operation op, u64 sequence) {
    return value.tag == magic && value.format == version && value.op == op && value.sequence == sequence &&
        !has_bytes(value.reserved, sizeof(value.reserved));
}

inline operation for_scenario(anchor_guest::scenario mode) {
    switch (mode) {
    case anchor_guest::scenario::user_named_read: return operation::select;
    case anchor_guest::scenario::user_named_put: return operation::put;
    case anchor_guest::scenario::user_named_erase: return operation::erase;
    default: return {};
    }
}

inline bool empty(const named_resource_request& value) {
    return !has_bytes(reinterpret_cast<const u8*>(&value), sizeof(value));
}

inline bool selection(const packet& value, operation op) {
    return header(value, op, 1) && value.result == 0 && valid_named_request(value.fields, op == operation::put) &&
        (op != operation::erase || value.fields.generation);
}

inline bool outcome(const packet& value, const packet& selected) {
    if (!header(value, selected.op, 2)) { return false; }
    if (value.result != 1) {
        const auto denied = value.result == user_login::denied || value.result == user_login::resource_denied;
        return empty(value.fields) && (selected.op == operation::select ? denied : value.result == conflict);
    }
    const auto& result = value.fields;
    const auto& requested = selected.fields;
    if (!valid_named_request(result, selected.op == operation::select) || !result.generation ||
        result.length != requested.length || __builtin_memcmp(result.name, requested.name, result.length) != 0) {
        return false;
    }
    return selected.op == operation::put ? result.generation > requested.generation :
        !requested.generation || result.generation == requested.generation;
}
}
