// SPDX-License-Identifier: Apache-2.0
#include <xos/channel_io.hpp>
#include <xos/terminal_client.hpp>

namespace xos::terminal {
void close(client& session) {
    if (session.send_handle != 0) (void)sdk::channel_close(session.send_handle);
    if (session.receive_handle != 0) (void)sdk::channel_close(session.receive_handle);
    session = {};
}

i64 connect(client& session, u64 controller_pid, u64 service_pid) {
    if (session.send_handle != 0 || session.receive_handle != 0 || session.controller_pid != 0 ||
        session.service_pid != 0 || controller_pid == 0 || service_pid == 0 ||
        controller_pid == service_pid) return process_error_invalid;
    u32 send = 0, receive = 0;
    for (u32 i = 0; i < 32; ++i) {
        channel_info info{};
        const i64 result = sdk::channel_get(i, info);
        if (result == thread_error_not_found) break;
        if (result != 0 || info.version != channel_version || info.size != sizeof(info))
            return process_error_state;
        if (info.controller_pid != controller_pid || info.peer_pid != service_pid) continue;
        if (info.rights == channel_send && send == 0) send = info.handle;
        else if (info.rights == channel_receive && receive == 0) receive = info.handle;
        else return process_error_state;
    }
    if (send == 0 || receive == 0 || send == receive) return process_error_denied;
    session.send_handle = send; session.receive_handle = receive;
    session.controller_pid = controller_pid; session.service_pid = service_pid;
    return 0;
}

i64 connect_startup(client& session, const startup_info* startup) {
    if (startup == nullptr || startup->magic != startup_magic || (startup->version != 2 && startup->version != 3) ||
        startup->size != sizeof(startup_info) || startup->reserved != startup_extension_offset)
        return process_error_invalid;
    const auto* extension = reinterpret_cast<const startup_extension*>(
        reinterpret_cast<const u8*>(startup) + startup_extension_offset);
    if (extension->magic != startup_extension_magic ||
        (extension->flags & startup_flag_terminal) == 0 || extension->reserved == 0)
        return process_error_denied;
    for (u32 i = 0; i < 32; ++i) {
        channel_info info{};
        const i64 result = sdk::channel_get(i, info);
        if (result == thread_error_not_found) break;
        if (result != 0 || info.version != channel_version || info.size != sizeof(info))
            return process_error_state;
        if (info.handle != extension->reserved || info.rights != channel_send) continue;
        const i64 connected = connect(session, info.controller_pid, info.peer_pid);
        if (connected != 0) return connected;
        if (session.send_handle == extension->reserved) {
            if (startup->version == 3) {
                const auto* state = reinterpret_cast<const startup_terminal_exec_extension*>(
                    reinterpret_cast<const u8*>(startup) + startup_terminal_exec_offset);
                if (state->magic != startup_terminal_exec_magic || state->next_sequence == 0) {
                    close(session); return process_error_state;
                }
                session.next_sequence = state->next_sequence;
            }
            return 0;
        }
        close(session); return process_error_denied;
    }
    return process_error_denied;
}

namespace {
bool known_error(i64 result) {
    if (result >= 0) return true;
    switch (result) {
    case -1: case -2: case -3: case -4: case -5: case -6: case -7:
    case -10: case -11: case -12: case -13: case -14: case -15: case -16:
    case -17: case -18: case interrupted: return true;
    default: return false;
    }
}
i64 deadline_status(u64 deadline_ns) {
    if (deadline_ns == thread_deadline_infinite) return 0;
    const i64 now = sdk::syscall(sys_clock_monotonic);
    if (now < 0) return now;
    return static_cast<u64>(now) >= deadline_ns ? thread_error_timeout : 0;
}
i64 exchange(client& session, request& message, response& reply, u64 deadline_ns = thread_deadline_infinite) {
    if (session.send_handle == 0 || session.receive_handle == 0 || session.next_sequence == 0) {
        close(session);
        return process_error_state;
    }
    if (const i64 expired = deadline_status(deadline_ns); expired != 0) return expired;
    message.version = version; message.size = sizeof(message); message.sequence = session.next_sequence++;
    i64 result = sdk::channel_send_wait(session.send_handle, &message, sizeof(message), deadline_ns);
    if (result == 0)
        result = sdk::channel_receive_wait(session.receive_handle, &reply, sizeof(reply), deadline_ns);
    if (result < 0) {
        close(session);
        // This exchange was using a session pair, rather than discovering
        // authority. Revocation invalidates its transport, including a close
        // racing with wait/send/receive. A complete denied service reply is
        // handled separately below and retains its original status.
        return result == process_error_denied ? pipe_error_broken : result;
    }
    if (result != static_cast<i64>(sizeof(reply)) || reply.version != version ||
        reply.size != sizeof(reply) || reply.sequence != message.sequence || reply.length > data_bytes ||
        reply.reserved != 0 || !known_error(reply.result)) {
        close(session); return process_error_state;
    }
    // A complete matching reply synchronizes the parent transport even when
    // its caller's startup deadline has elapsed and the child must be aborted.
    return deadline_status(deadline_ns);
}
}

i64 register_fork_until(client& session, const channel_fork_pair& pair, u64 deadline_ns) {
    if (pair.version != channel_version || pair.size != sizeof(pair) || pair.child_pid == 0 ||
        pair.source_send != session.send_handle || pair.source_receive != session.receive_handle ||
        pair.child_send == 0 || pair.child_receive == 0 || pair.child_send == pair.child_receive)
        return process_error_invalid;
    const session_channels channels{pair.child_send, pair.child_receive, pair.child_pid};
    request message{}; response reply{};
    message.operation = static_cast<u32>(operation::fork_attach);
    message.length = sizeof(channels);
    const auto* bytes = reinterpret_cast<const u8*>(&channels);
    for (u32 i = 0; i < sizeof(channels); ++i) message.data[i] = bytes[i];
    const i64 result = exchange(session, message, reply, deadline_ns);
    if (result != 0) return result;
    if (reply.result > 0 || reply.length != 0) { close(session); return process_error_state; }
    return reply.result;
}

i64 register_fork(client& session, const channel_fork_pair& pair) {
    return register_fork_until(session, pair, thread_deadline_infinite);
}

i64 get_mode(client& session, mode& value) {
    request message{}; response reply{};
    message.operation = static_cast<u32>(operation::mode_get);
    const i64 transport = exchange(session, message, reply);
    if (transport != 0) return transport;
    if (reply.result < 0 && reply.length == 0) return reply.result;
    if (reply.result != 0 || reply.length != sizeof(mode)) { close(session); return process_error_state; }
    auto* bytes = reinterpret_cast<u8*>(&value);
    for (u32 i = 0; i < sizeof(mode); ++i) bytes[i] = reply.data[i];
    if (!valid_mode(value)) { close(session); return process_error_state; }
    return 0;
}

i64 set_mode(client& session, const mode& value, mode_action action) {
    if (!valid_mode(value)) return thread_error_unsupported;
    if (action != mode_action::now && action != mode_action::drain && action != mode_action::drain_flush_input)
        return process_error_invalid;
    request message{}; response reply{};
    message.operation = static_cast<u32>(operation::mode_set);
    message.deadline_ns = static_cast<u32>(action);
    message.length = sizeof(value);
    const auto* bytes = reinterpret_cast<const u8*>(&value);
    for (u32 i = 0; i < sizeof(value); ++i) message.data[i] = bytes[i];
    const i64 transport = exchange(session, message, reply);
    if (transport != 0) return transport;
    if (reply.result > 0 || reply.length != 0) { close(session); return process_error_state; }
    return reply.result;
}

i64 flush_input(client& session) {
    request message{}; response reply{};
    message.operation = static_cast<u32>(operation::flush_input);
    const i64 transport = exchange(session, message, reply);
    if (transport != 0) return transport;
    if (reply.result > 0 || reply.length != 0) { close(session); return process_error_state; }
    return reply.result;
}

i64 drain(client& session) {
    request message{}; response reply{};
    message.operation = static_cast<u32>(operation::drain);
    const i64 transport = exchange(session, message, reply);
    if (transport != 0) return transport;
    if (reply.result > 0 || reply.length != 0) { close(session); return process_error_state; }
    return reply.result;
}

i64 read_mode(client& session, void* data, u32 length) {
    if (data == nullptr && length != 0) return process_error_invalid;
    if (length > data_bytes) length = data_bytes;
    request message{}; response reply{};
    message.operation = static_cast<u32>(operation::read_mode); message.length = length;
    const i64 transport = exchange(session, message, reply);
    if (transport != 0) return transport;
    if (reply.result > static_cast<i64>(length) ||
        (reply.result > 0 ? reply.length != static_cast<u32>(reply.result) : reply.length != 0)) {
        close(session); return process_error_state;
    }
    auto* output = static_cast<u8*>(data);
    for (u32 i = 0; i < reply.length; ++i) output[i] = reply.data[i];
    return reply.result;
}

i64 wait_readable(client& session, u64 deadline_ns) {
    request message{}; response reply{};
    message.operation = static_cast<u32>(operation::wait_readable); message.deadline_ns = deadline_ns;
    const i64 result = exchange(session, message, reply);
    if (result != 0) return result;
    if (reply.length != 0 || reply.result > 1) { close(session); return process_error_state; }
    return reply.result;
}

i64 read_until(client& session, void* data, u32 length, u64 deadline_ns) {
    if (data == nullptr && length != 0) return process_error_invalid;
    if (length > data_bytes) length = data_bytes;
    request message{}; response reply{};
    message.operation = static_cast<u32>(operation::read_until);
    message.length = length; message.deadline_ns = deadline_ns;
    const i64 result = exchange(session, message, reply);
    if (result != 0) return result;
    if (reply.result > static_cast<i64>(length) || (length != 0 && reply.result == 0) ||
        (reply.result > 0 ? reply.length != static_cast<u32>(reply.result) : reply.length != 0)) {
        close(session); return process_error_state;
    }
    auto* output = static_cast<u8*>(data);
    for (u32 i = 0; i < reply.length; ++i) output[i] = reply.data[i];
    return reply.result;
}

i64 write_until(client& session, const void* data, u32 length, u64 deadline_ns) {
    if (data == nullptr && length != 0) return process_error_invalid;
    if (length > data_bytes) length = data_bytes;
    request message{}; response reply{};
    message.operation = static_cast<u32>(operation::write_until);
    message.length = length; message.deadline_ns = deadline_ns;
    const auto* input = static_cast<const u8*>(data);
    for (u32 i = 0; i < length; ++i) message.data[i] = input[i];
    const i64 result = exchange(session, message, reply);
    if (result != 0) return result;
    if (reply.result > static_cast<i64>(length) || (length != 0 && reply.result == 0) || reply.length != 0) {
        close(session); return process_error_state;
    }
    return reply.result;
}
}
