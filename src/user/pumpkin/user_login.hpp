// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "native_ipc.hpp"
#include "generation_guest.hpp"

namespace xos::user::pumpkin::user_login {
inline constexpr u32 magic = 0x31554b50; // PKU1
inline constexpr u16 version = 1;
inline constexpr u8 denied = 2;
inline constexpr u8 resource_denied = 3;
inline constexpr u8 duplicate_enrollment = 6;
enum class operation : u8 { issue = 1, submit };

// Private, separate from the generation records even though both use the
// exclusive UART. One credential exchange may occur during a user boot.
struct packet {
    u32 tag = magic;
    u16 format = version;
    operation op{};
    u8 reserved = 0;
    u64 sequence = 1;
    wire_id identity;
    credential key;
    u8 padding[72]{};

    ~packet() { wipe_bytes(&key, sizeof(key)); }
};
static_assert(sizeof(packet) == sizeof(anchor_guest::packet));

inline constexpr u32 account_magic = 0x314f4b50; // PKO1
struct account_packet {
    u32 tag = account_magic;
    u16 format = version;
    anchor_guest::scenario op{};
    u8 initialize = 0;
    u64 sequence = 1;
    u32 length = 0;
    char name[name_limit]{};
    u8 reserved[92]{};
};
static_assert(sizeof(account_packet) == sizeof(anchor_guest::packet));

inline bool header(const account_packet& value, anchor_guest::scenario mode, u64 sequence) {
    return value.tag == account_magic && value.format == version && value.op == mode &&
        value.sequence == sequence && !has_bytes(value.reserved, sizeof(value.reserved));
}

inline bool selected_account(const account_packet& value, anchor_guest::scenario mode) {
    return header(value, mode, 1) && value.initialize <= (mode == anchor_guest::scenario::user_enroll) &&
        value.length <= sizeof(value.name) && valid_name({value.name, value.length}) &&
        !has_bytes(reinterpret_cast<const u8*>(value.name) + value.length, sizeof(value.name) - value.length);
}

inline bool enrollment_ready(const account_packet& value) {
    return header(value, anchor_guest::scenario::user_enroll, 2) && !value.initialize && !value.length &&
        !has_bytes(reinterpret_cast<const u8*>(value.name), sizeof(value.name));
}

inline bool header(const packet& value, operation operation, u64 sequence) {
    return value.tag == magic && value.format == version && value.op == operation && value.reserved == 0 &&
        value.sequence == sequence && !has_bytes(value.padding, sizeof(value.padding));
}

inline bool same_identity(const wire_id& left, const wire_id& right) {
    return left.number == right.number && left.scope == right.scope;
}

inline bool reserve_credential_destination(const anchor_guest::pair& proxy) {
    account_packet request{}, reply{};
    request.op = anchor_guest::scenario::user_enroll;
    request.sequence = 2;
    const auto end = anchor_guest::deadline();
    return end != 0 && sdk::channel_send_wait(proxy.transmit, &request, sizeof(request), end) == 0 &&
        sdk::channel_receive_wait(proxy.receive, &reply, sizeof(reply), end) == sizeof(reply) &&
        enrollment_ready(reply);
}

inline bool exchange_with_operator(const anchor_guest::pair& proxy, const packet& request, packet& reply) {
    const auto end = anchor_guest::deadline();
    if (end == 0 || sdk::channel_send_wait(proxy.transmit, &request, sizeof(request), end) != 0 ||
        sdk::channel_receive_wait(proxy.receive, &reply, sizeof(reply), end) != sizeof(reply) ||
        !header(reply, request.op, request.sequence) || !same_identity(reply.identity, request.identity)) return false;
    // Clear both kernel mail slots after the private exchange. The proxy does
    // not forward this second, secret-free round trip to the operator.
    packet clear{}, ack{};
    clear.op = request.op;
    clear.sequence = 2;
    clear.identity = request.identity;
    return sdk::channel_send_wait(proxy.transmit, &clear, sizeof(clear), end) == 0 &&
        sdk::channel_receive_wait(proxy.receive, &ack, sizeof(ack), end) == sizeof(ack) &&
        header(ack, clear.op, clear.sequence) && same_identity(ack.identity, clear.identity) &&
        !has_bytes(ack.key.bytes, secret_bytes);
}
}
