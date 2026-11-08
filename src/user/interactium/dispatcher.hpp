// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "service.hpp"

namespace xos::interactium {

inline constexpr u32 max_frame_bytes = 800u * 600u * 4u;
inline constexpr u32 max_wire_payload = 4096u - sizeof(wire_header);

enum class dispatch_result : i32 {
    ok = 0,
    malformed = -1,
    denied = -2,
    busy = -3,
    unsupported = -4,
    resources = -5,
};

// This class is transport-neutral: request and response are contiguous byte
// buffers supplied by an endpoint adapter. It owns no client memory.
class protocol_dispatcher {
    struct pending_frame {
        bool active = false;
        window_id window{};
        u64 serial = 0;
        u32 width = 0;
        u32 height = 0;
        u32 stride = 0;
        u64 bytes = 0;
    };

    service* service_ = nullptr;
    u64 owner_ = 0;
    session_token session_{};
    u64 last_sequence_ = 0;
    pending_frame frame_{};

    bool session_matches(const wire_header& header) const;
    i32 write_reply(const wire_header& request, message_type type, window_id object,
                    i64 result, const void* payload, u32 payload_length,
                    u8* response, u32 response_capacity, u32& response_size) const;
    i32 write_status(const wire_header& request, window_id object, i64 result,
                     u8* response, u32 response_capacity, u32& response_size) const;

public:
    protocol_dispatcher(service& service, u64 authenticated_owner)
        : service_(&service), owner_(authenticated_owner) {}
    void bind(service& service, u64 authenticated_owner) {
        service_ = &service;
        owner_ = authenticated_owner;
        session_ = {};
        last_sequence_ = 0;
        frame_ = {};
    }

    i32 dispatch(const u8* request, u32 request_size, u8* response,
                 u32 response_capacity, u32& response_size);
    void transport_closed();
    session_token session() const { return session_; }
    bool connected() const { return session_.value != 0; }
};

} // namespace xos::interactium
