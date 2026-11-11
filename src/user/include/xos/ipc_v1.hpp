// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/ipc_v1_abi.hpp>
#include <xos/sdk.hpp>

namespace xos::ipc_v1 {
inline i64 query_features(ipc_v1_feature_query& output) {
    output = {};
    output.header.version = ipc_v1_version;
    output.header.size = sizeof(output);
    const i64 result = sdk::syscall(sys_ipc_v1,
        static_cast<u64>(ipc_v1_action::query_features),
        reinterpret_cast<u64>(&output), 0);
    if (result != 0) return result;
    if (output.known_features != ipc_v1_feature_known_mask ||
        (output.supported_features & ~output.known_features) != 0 ||
        output.max_message_bytes != ipc_v1_max_message_bytes ||
        output.max_handles_per_process != ipc_v1_max_handles_per_process ||
        output.max_endpoints_system != ipc_v1_max_endpoints_system ||
        output.max_pending_calls != ipc_v1_max_pending_calls ||
        output.max_queue_per_endpoint != ipc_v1_max_queue_per_endpoint ||
        output.max_reply_tokens_per_process != ipc_v1_max_reply_tokens_per_process ||
        output.reserved[0] != 0 || output.reserved[1] != 0) {
        output = {};
        return static_cast<i64>(ipc_v1_error::state);
    }
    return 0;
}

inline bool supports(ipc_v1_feature feature, const ipc_v1_feature_query& query) {
    return (query.supported_features & static_cast<u64>(feature)) != 0;
}
}
