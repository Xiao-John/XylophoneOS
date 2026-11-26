// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "../../../src/user/pumpkin/disk_test_store.hpp"
#include "../../../src/user/pumpkin/native_ipc.hpp"

namespace xos::user::pumpkin::durable_probe {

inline constexpr char account[] = "alice";
inline constexpr char rendezvous[] = "pumpkin-p2-bootstrap";
inline constexpr char daemon_image[] = "pumpkin_durable";

struct dash_offer {
    u64 daemon = 0;
    credential key;
};
static_assert(sizeof(dash_offer) == 40);

inline wire_request operation_request(wire_operation op, bool named = false) {
    wire_request request;
    request.operation = op;
    if (named) {
        request.name_length = sizeof(account) - 1;
        __builtin_memcpy(request.name, account, sizeof(account));
    }
    return request;
}

inline bool expect(ipc_client& client, wire_request& request, wire_reply& response, wire_status expected) {
    return client.call(request, response) == exchange::received && response.result == expected;
}

inline bool bind_ordinary(ipc_client& client, u64 daemon) {
    const i64 start = monotonic_now();
    if (start < 0) {
        return false;
    }
    const u64 deadline = static_cast<u64>(start) + max_request_ns;
    for (;;) {
        ipc_channel channel{};
        const i64 connected = sdk::ipc_name_connect(disk_test_service, channel);
        if (connected == 0) {
            return client.bind(channel, daemon);
        }
        const i64 now = monotonic_now();
        if (connected != ipc_error_name_not_found || now < 0 ||
            static_cast<u64>(now) >= deadline || !sleep_tick(static_cast<u64>(now))) {
            return false;
        }
    }
}

inline bool login(ipc_client& client, const credential& key, wire_reply& reply, wire_status expected) {
    auto request = operation_request(wire_operation::authenticate, true);
    request.key = key;
    const bool success = expect(client, request, reply, expected);
    wipe_bytes(&request, sizeof(request));
    return success;
}

}
