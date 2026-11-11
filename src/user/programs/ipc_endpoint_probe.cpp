// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>

extern "C" int xos_user_main(const xos::startup_info*) {
    using namespace xos;
    ipc_channel channel{};
    if (sdk::ipc_channel_create(0, channel) != 0 || channel.send == 0 || channel.receive == 0) {
        return 10;
    }
    constexpr char payload[] = "endpoint-probe";
    if (sdk::ipc_wait(channel.send, ipc_wait_mode::send) != 0 ||
        sdk::ipc_wait(channel.send, ipc_wait_mode::receive) >= 0 ||
        sdk::ipc_send(channel.receive, payload, sizeof(payload)) >= 0 ||
        sdk::ipc_send(channel.send, payload, sizeof(payload)) != 0 ||
        sdk::ipc_send(channel.send, payload, sizeof(payload)) != ipc_error_full) {
        return 11;
    }
    if (sdk::ipc_channel_revoke(channel.send) != 0 ||
        sdk::ipc_send(channel.send, payload, sizeof(payload)) >= 0) {
        return 12;
    }
    sdk::print("IPC_ENDPOINT_PASS\n");
    return 0;
}
