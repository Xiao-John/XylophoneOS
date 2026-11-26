// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "native_ipc.hpp"
#include "generation_guest.hpp"

namespace xos::user::pumpkin::user_login {
inline constexpr u32 magic = 0x31554b50; // PKU1
inline constexpr u16 version = 1;
inline constexpr u8 denied = 2;
inline constexpr u8 resource_denied = 3;
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

inline bool header(const packet& value, operation operation, u64 sequence) {
    return value.tag == magic && value.format == version && value.op == operation && value.reserved == 0 &&
        value.sequence == sequence && !has_bytes(value.padding, sizeof(value.padding));
}

inline bool same_identity(const wire_id& left, const wire_id& right) {
    return left.number == right.number && left.scope == right.scope;
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
