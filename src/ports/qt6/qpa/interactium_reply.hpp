// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <xos/interactium_abi.hpp>
#include <xos/process_abi.hpp>

namespace xos::qt {

// The transport buffer can hold a full IPC message; QPA's caller buffers hold
// only one reply payload. Validate both the operation's shape and that smaller
// capacity before publishing any output. This is not a new wire protocol.
inline i64 decode_interactium_reply(const u8* response, i64 received,
                                    const interactium::wire_header& request,
                                    interactium::wire_header& reply, u8* reply_payload,
                                    u32 reply_capacity, u32& reply_length) {
    using namespace interactium;
    if (received < static_cast<i64>(sizeof(wire_header))) return process_error_state;
    if (response == nullptr || received > process_pipe_bytes || reply_payload == nullptr)
        return process_error_invalid;

    wire_header candidate{};
    for (u32 i = 0; i < sizeof(candidate); ++i)
        reinterpret_cast<u8*>(&candidate)[i] = response[i];
    const auto length = static_cast<u32>(received);
    if (candidate.version != protocol_version || candidate.size != length ||
        candidate.sequence != request.sequence ||
        candidate.payload_length != length - sizeof(wire_header) ||
        (request.type != message_type::hello && candidate.session != request.session) ||
        candidate.payload_length > reply_capacity) return process_error_invalid;

    bool shape = candidate.type == message_type::ack &&
                 candidate.payload_length == sizeof(status_payload);
    if (request.type == message_type::hello)
        shape = candidate.type == message_type::hello_reply &&
                candidate.payload_length == sizeof(hello_reply_payload);
    else if (request.type == message_type::input)
        shape = shape || (candidate.type == message_type::input &&
                          candidate.payload_length == sizeof(input_payload));
    if (!shape) return process_error_invalid;

    for (u32 i = 0; i < candidate.payload_length; ++i)
        reply_payload[i] = response[sizeof(wire_header) + i];
    reply = candidate;
    reply_length = candidate.payload_length;
    return 0;
}

} // namespace xos::qt
