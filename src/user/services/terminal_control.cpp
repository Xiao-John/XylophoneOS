// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/terminal_control.hpp>
#include <xos/thread_abi.hpp>

namespace xos::terminal {
void close(control& session) {
    if (session.send_handle != 0) (void)sdk::channel_close(session.send_handle);
    if (session.receive_handle != 0) (void)sdk::channel_close(session.receive_handle);
    session = {};
}

namespace {
i64 prepare(u64 child, void* context) {
    auto& session = *static_cast<control*>(context);
    const u64 parent = sdk::pid();
    channel_create request{channel_version, sizeof(channel_create), parent, child,
                           sizeof(terminal::request), 0};
    i64 result = sdk::channel_open(request);
    if (result <= 0) return result < 0 ? result : process_error_state;
    session.send_handle = static_cast<u32>(result);
    request.sender_pid = child; request.receiver_pid = parent;
    request.capacity = sizeof(terminal::response);
    result = sdk::channel_open(request);
    if (result <= 0) return result < 0 ? result : process_error_state;
    session.receive_handle = static_cast<u32>(result);
    return sdk::pio_grant(pio_grant_action::grant, child, pio_resource_com1);
}
}

i64 start(control& session, const char* path) {
    if (path == nullptr || session.send_handle != 0 || session.receive_handle != 0 || session.child != 0)
        return process_error_invalid;
    sdk::spawn_options options{};
    for (u32 i = 0; i < 3; ++i) options.stdio[i] = -2;
    options.prepare_child = prepare; options.prepare_context = &session;
    const char* argv[] = {path};
    const i64 child = sdk::spawn_file_options(path, 1, argv, options);
    if (child <= 0) { close(session); return child < 0 ? child : process_error_state; }
    session.child = static_cast<u64>(child);
    return child;
}

i64 exchange(control& session, request& message, response& reply) {
    if (session.child == 0 || session.send_handle == 0 || session.receive_handle == 0 ||
        session.next_sequence == 0) return process_error_state;
    message.version = version; message.size = sizeof(message); message.sequence = session.next_sequence++;
    i64 result = sdk::channel_wait(session.send_handle, thread_deadline_infinite);
    if (result == 0) result = sdk::ipc_send(session.send_handle, &message, sizeof(message));
    if (result != 0) return result;
    result = sdk::channel_wait(session.receive_handle, thread_deadline_infinite);
    if (result != 0) return result;
    result = sdk::ipc_recv(session.receive_handle, &reply, sizeof(reply));
    if (result != static_cast<i64>(sizeof(reply)) || reply.version != version ||
        reply.size != sizeof(reply) || reply.sequence != message.sequence ||
        reply.length > data_bytes) return process_error_state;
    return 0;
}
}
