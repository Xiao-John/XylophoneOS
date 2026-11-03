// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/channel_io.hpp>
#include <xos/terminal_control.hpp>
#include <xos/thread_abi.hpp>

namespace xos::terminal {
namespace {
void invalidate_channels(control& session) {
    if (session.send_handle != 0) (void)sdk::channel_close(session.send_handle);
    if (session.receive_handle != 0) (void)sdk::channel_close(session.receive_handle);
    session.send_handle = 0;
    session.receive_handle = 0;
}
}
void close(control& session) {
    invalidate_channels(session);
    session = {};
}
void close(application& app) {
    if (app.incoming != 0) (void)sdk::channel_close(app.incoming);
    if (app.outgoing != 0) (void)sdk::channel_close(app.outgoing);
    app = {};
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

i64 submit(control& session, request& message) {
    if (session.child == 0 || session.send_handle == 0 || session.receive_handle == 0 ||
        session.next_sequence == 0) return process_error_state;
    if (session.outstanding >= 2) return process_error_busy;
    message.version = version; message.size = sizeof(message); message.sequence = session.next_sequence++;
    const i64 result = sdk::channel_send_wait(session.send_handle, &message, sizeof(message), thread_deadline_infinite);
    if (result != 0) { invalidate_channels(session); return result; }
    ++session.outstanding;
    return 0;
}

i64 receive(control& session, response& reply) {
    if (session.child == 0 || session.send_handle == 0 || session.receive_handle == 0 ||
        session.outstanding == 0) return process_error_state;
    const i64 result = sdk::channel_receive_wait(session.receive_handle, &reply, sizeof(reply), thread_deadline_infinite);
    if (result < 0) { invalidate_channels(session); return result; }
    if (result != static_cast<i64>(sizeof(reply)) || reply.version != version ||
        reply.size != sizeof(reply) || reply.sequence != session.next_response ||
        reply.length > data_bytes) { invalidate_channels(session); return process_error_state; }
    ++session.next_response;
    --session.outstanding;
    return 0;
}

i64 exchange(control& session, request& message, response& reply) {
    if (session.child == 0 || session.send_handle == 0 || session.receive_handle == 0)
        return process_error_state;
    if (session.outstanding != 0) return process_error_busy;
    i64 result = submit(session, message);
    if (result != 0) return result;
    result = receive(session, reply);
    if (result != 0) return result;
    if (reply.sequence != message.sequence) { invalidate_channels(session); return process_error_state; }
    return 0;
}

i64 read_until(control& session, void* data, u32 length, u64 deadline_ns) {
    if (data == nullptr && length != 0) return process_error_invalid;
    if (length > data_bytes) length = data_bytes;
    request message{}; response reply{};
    message.operation = static_cast<u32>(operation::read_until);
    message.length = length; message.deadline_ns = deadline_ns;
    const i64 transport = exchange(session, message, reply);
    if (transport != 0) return transport;
    if (reply.result > static_cast<i64>(length) ||
        (reply.result > 0 ? reply.length != static_cast<u32>(reply.result) : reply.length != 0)) {
        invalidate_channels(session); return process_error_state;
    }
    auto* output = static_cast<u8*>(data);
    for (u32 i = 0; i < reply.length; ++i) output[i] = reply.data[i];
    return reply.result;
}

i64 write_until(control& session, const void* data, u32 length, u64 deadline_ns) {
    if (data == nullptr && length != 0) return process_error_invalid;
    if (length > data_bytes) length = data_bytes;
    request message{}; response reply{};
    message.operation = static_cast<u32>(operation::write_until);
    message.length = length; message.deadline_ns = deadline_ns;
    const auto* input = static_cast<const u8*>(data);
    for (u32 i = 0; i < length; ++i) message.data[i] = input[i];
    const i64 transport = exchange(session, message, reply);
    if (transport != 0) return transport;
    if (reply.result > static_cast<i64>(length) || reply.length != 0) {
        invalidate_channels(session); return process_error_state;
    }
    return reply.result;
}

i64 attach(control& session, application& app, u64 child) {
    if (session.child == 0 || child == 0 || app.incoming != 0 || app.outgoing != 0 || app.peer != 0)
        return process_error_invalid;
    channel_create request{channel_version, sizeof(channel_create), child, session.child,
                           sizeof(terminal::request), 0};
    i64 result = sdk::channel_open(request);
    if (result <= 0) return result < 0 ? result : process_error_state;
    app.incoming = static_cast<u32>(result);
    request.sender_pid = session.child; request.receiver_pid = child;
    request.capacity = sizeof(terminal::response);
    result = sdk::channel_open(request);
    if (result <= 0) { close(app); return result < 0 ? result : process_error_state; }
    app.outgoing = static_cast<u32>(result); app.peer = child;
    const session_channels channels{app.incoming, app.outgoing, child};
    terminal::request message{}; terminal::response reply{};
    message.operation = static_cast<u32>(operation::attach);
    message.length = sizeof(channels);
    const auto* bytes = reinterpret_cast<const u8*>(&channels);
    for (u32 i = 0; i < sizeof(channels); ++i) message.data[i] = bytes[i];
    result = exchange(session, message, reply);
    if (result == 0) result = reply.result;
    if (result != 0) close(app);
    return result;
}

i64 detach(control& session, application& app) {
    if (app.incoming == 0 || app.outgoing == 0 || app.peer == 0) return process_error_state;
    terminal::request message{}; terminal::response reply{};
    message.operation = static_cast<u32>(operation::detach);
    i64 result = exchange(session, message, reply);
    if (result == 0) result = reply.result;
    close(app);
    return result;
}
}
