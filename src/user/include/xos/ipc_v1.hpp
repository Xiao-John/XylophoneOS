// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/ipc_v1_abi.hpp>
#include <xos/sdk.hpp>

namespace xos::ipc_v1 {
template<class T>
inline i64 invoke(ipc_v1_action action, T& request) {
    request.header.version = ipc_v1_version;
    request.header.size = sizeof(request);
    request.header.reserved = 0;
    return sdk::syscall(sys_ipc_v1, static_cast<u64>(action),
                       reinterpret_cast<u64>(&request), 0);
}

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

inline i64 endpoint_create(u32 rights, u64& handle) {
    ipc_v1_endpoint_create request{};
    request.rights = rights;
    const i64 result = invoke(ipc_v1_action::endpoint_create, request);
    handle = result == 0 ? request.handle_out : 0;
    return result;
}

inline i64 endpoint_delegate(u64 handle, u64 target_pid, u64 badge, u32 rights,
                             u64& delegated_handle) {
    ipc_v1_endpoint_delegate request{};
    request.handle = handle; request.target_pid = target_pid;
    request.badge = badge; request.rights = rights;
    const i64 result = invoke(ipc_v1_action::endpoint_delegate, request);
    delegated_handle = result == 0 ? request.handle_out : 0;
    return result;
}

inline i64 endpoint_close(u64 handle) {
    ipc_v1_endpoint_close request{};
    request.handle = handle;
    return invoke(ipc_v1_action::endpoint_close, request);
}

inline i64 notification_create(u32 rights, u64& handle) {
    ipc_v1_object_create request{}; request.rights = rights;
    const i64 result = invoke(ipc_v1_action::notification_create, request);
    handle = result == 0 ? request.handle_out : 0; return result;
}
inline i64 notification_delegate(u64 handle, u64 target_pid, u64 badge, u32 rights, u64& output) {
    ipc_v1_object_delegate request{}; request.handle=handle; request.target_pid=target_pid;
    request.badge=badge; request.rights=rights;
    const i64 result=invoke(ipc_v1_action::notification_delegate, request);
    output=result == 0 ? request.handle_out : 0; return result;
}
inline i64 notification_signal(u64 handle) {
    ipc_v1_notification_signal request{}; request.handle=handle;
    return invoke(ipc_v1_action::notification_signal, request);
}
inline i64 notification_close(u64 handle) {
    ipc_v1_object_close request{}; request.handle = handle;
    return invoke(ipc_v1_action::notification_close, request);
}
inline i64 notification_wait(u64 handle, u64 deadline_ns, u64& bits) {
    ipc_v1_notification_wait request{}; request.handle=handle; request.deadline_ns=deadline_ns;
    const i64 result=invoke(ipc_v1_action::notification_wait, request);
    bits=result == 0 ? request.bits_out : 0; return result;
}
inline i64 wait_set_create(u32 rights, u64& handle) {
    ipc_v1_object_create request{}; request.rights=rights;
    const i64 result=invoke(ipc_v1_action::wait_set_create, request);
    handle=result == 0 ? request.handle_out : 0; return result;
}
inline i64 wait_set_delegate(u64 handle, u64 target_pid, u64 badge, u32 rights, u64& output) {
    ipc_v1_object_delegate request{}; request.handle=handle; request.target_pid=target_pid;
    request.badge=badge; request.rights=rights;
    const i64 result=invoke(ipc_v1_action::wait_set_delegate, request);
    output=result == 0 ? request.handle_out : 0; return result;
}
inline i64 wait_set_close(u64 handle) {
    ipc_v1_object_close request{}; request.handle=handle;
    return invoke(ipc_v1_action::wait_set_close, request);
}
inline i64 wait_set_add(ipc_v1_wait_set_add& request) {
    request.source_id_out=0; return invoke(ipc_v1_action::wait_set_add, request);
}
inline i64 wait_set_remove(ipc_v1_wait_set_remove& request) {
    return invoke(ipc_v1_action::wait_set_remove, request);
}
inline i64 wait_set_wait(ipc_v1_wait_set_wait& request) {
    request.count_out=0; return invoke(ipc_v1_action::wait_set_wait, request);
}

inline i64 call(ipc_v1_call& request) {
    request.reply_length_out = request.phase_out = 0;
    request.reply_label_out = 0;
    return invoke(ipc_v1_action::call, request);
}
inline i64 receive(ipc_v1_receive& request) {
    request.message_length_out = 0;
    request.label_out = request.badge_out = request.reply_token_out = 0;
    return invoke(ipc_v1_action::receive, request);
}
inline i64 reply(ipc_v1_reply& request) { return invoke(ipc_v1_action::reply, request); }
inline i64 reply_receive(ipc_v1_reply_receive& request) {
    request.reply_consumed_out = request.receive_length_out = 0;
    request.label_out = request.badge_out = request.next_reply_token_out = 0;
    return invoke(ipc_v1_action::reply_receive, request);
}

inline bool supports(ipc_v1_feature feature, const ipc_v1_feature_query& query) {
    return (query.supported_features & static_cast<u64>(feature)) != 0;
}
}
