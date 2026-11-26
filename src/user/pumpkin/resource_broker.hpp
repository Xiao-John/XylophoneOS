// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "resource_bridge.hpp"
#include "sealed_blob.hpp"

namespace xos::user::pumpkin {

inline constexpr char broker_service_name[] = "pumpkin-sealed-broker";
inline constexpr u64 broker_object_number = 1;

// These boot frames are accepted only on the broker's authenticated parent
// channel. The runtime broker endpoint never sees a credential or a label.
struct broker_configuration {
    u32 version = wire_version;
    u32 length = 0;
    u64 daemon = 0;
    identity_id owner{};
    nonce incarnation{};
    u8 bytes[sealed_blob_capacity]{};
};
struct broker_ready {
    u32 version = wire_version;
    u32 reserved = 0;
    resource_broker_grant grant{};
};
struct broker_opened {
    u32 version = wire_version;
    u32 reserved = 0;
    u64 connection = 0;
};
struct broker_read {
    u32 version = wire_version;
    u32 reserved = 0;
    u64 object = 0;
    u64 deadline = 0;
    wire_id ticket{};
};
struct broker_data {
    u32 version = wire_version;
    wire_status result = wire_status::denied;
    sealed_blob_reply data{};
};
static_assert(sizeof(broker_configuration) == 312 && sizeof(broker_ready) == 24 &&
              sizeof(broker_opened) == 16 && sizeof(broker_read) == 48 && sizeof(broker_data) == 268);

template<class Frame>
bool receive_broker_frame(const ipc_channel& pair, Frame& frame, u64 deadline) {
    for (;;) {
        const auto now = monotonic_now();
        if (now < 0 || static_cast<u64>(now) >= deadline) { return false; }
        const auto result = sdk::ipc_recv(pair.receive, &frame, sizeof(frame));
        if (result == sizeof(frame)) { return true; }
        if (result != process_error_would_block || !sleep_tick(static_cast<u64>(now))) { return false; }
    }
}

}
