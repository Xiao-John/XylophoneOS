// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/sdk.hpp>
#include <xos/interactium_abi.hpp>
#include <xos/thread_abi.hpp>

namespace xos::interactium {

// One serialized transaction per object. Every wait uses the caller's original
// absolute deadline. Failure closes this session: mutations are never replayed.
class client {
    ipc_channel channel_{};
    u64 service_pid_ = 0, session_ = 0, sequence_ = 0;

    static void copy(void* out, const void* in, u32 size) {
        auto* destination = static_cast<u8*>(out);
        const auto* source = static_cast<const u8*>(in);
        for (u32 i = 0; i < size; ++i) destination[i] = source[i];
    }
    bool peer_matches() const {
        u64 send_peer = 0, receive_peer = 0;
        return service_pid_ != 0 && sdk::ipc_endpoint_peer(channel_.send, send_peer) == 0 &&
               sdk::ipc_endpoint_peer(channel_.receive, receive_peer) == 0 &&
               send_peer == service_pid_ && receive_peer == service_pid_;
    }
    i64 fail(i64 result) { close(); return result; }

public:
    client() = default;
    client(const client&) = delete;
    client& operator=(const client&) = delete;
    ~client() { close(); }
    u64 session() const { return session_; }
    u64 service_pid() const { return service_pid_; }
    void close() {
        if (channel_.send != 0) (void)sdk::ipc_channel_close(channel_.send);
        channel_ = {}; service_pid_ = session_ = sequence_ = 0;
    }

    i64 exchange(message_type type, u64 object, const void* payload, u32 size,
                 const void* pixels, u32 pixel_bytes, wire_header& reply,
                 void* reply_body, u32 reply_capacity, u32& reply_bytes, u64 deadline) {
        reply = {}; reply_bytes = 0;
        const u64 total = sizeof(wire_header) + u64(size) + pixel_bytes;
        if (total > 4096 || (size && !payload) || (pixel_bytes && !pixels) || !reply_body ||
            !peer_matches() || sequence_ == ~u64(0)) return fail(process_error_invalid);
        if (static_cast<u64>(sdk::syscall(sys_clock_monotonic)) >= deadline)
            return fail(thread_error_timeout);
        alignas(8) u8 buffer[4096]{};
        const wire_header request{protocol_version, u32(total), type, 0, ++sequence_,
                                  session_, object, size + pixel_bytes, 0};
        copy(buffer, &request, sizeof(request));
        if (size) copy(buffer + sizeof(request), payload, size);
        if (pixel_bytes) copy(buffer + sizeof(request) + size, pixels, pixel_bytes);
        i64 result = sdk::ipc_wait_until(channel_.send, ipc_wait_mode::send, deadline);
        if (result == 0) result = sdk::ipc_send(channel_.send, buffer, total);
        if (result == 0) result = sdk::ipc_wait_until(channel_.receive, ipc_wait_mode::receive, deadline);
        if (result != 0) return fail(result);
        result = sdk::ipc_recv(channel_.receive, buffer, sizeof(buffer));
        if (result < i64(sizeof(wire_header)) || !peer_matches()) return fail(process_error_state);
        copy(&reply, buffer, sizeof(reply));
        if (reply.version != protocol_version || reply.size != u32(result) ||
            reply.sequence != request.sequence || reply.flags != 0 || reply.reserved != 0 ||
            reply.payload_length != u32(result) - sizeof(wire_header) ||
            reply.payload_length > reply_capacity ||
            (type != message_type::hello && reply.session != session_) ||
            (type != message_type::create_window && reply.object != object))
            return fail(process_error_invalid);
        if (static_cast<u64>(sdk::syscall(sys_clock_monotonic)) >= deadline)
            return fail(thread_error_timeout);
        reply_bytes = reply.payload_length;
        copy(reply_body, buffer + sizeof(wire_header), reply_bytes);
        return 0;
    }

    i64 open(u64 expected_service_pid, u64 deadline) {
        if (channel_.send != 0 || expected_service_pid == 0) return process_error_invalid;
        i64 result = sdk::ipc_name_connect("interactium", channel_);
        if (result != 0) return result;
        service_pid_ = expected_service_pid;
        const hello_payload hello{protocol_version, 0, 800, 600};
        hello_reply_payload body{}; wire_header reply{}; u32 bytes = 0;
        result = exchange(message_type::hello, 0, &hello, sizeof(hello), nullptr, 0,
                          reply, &body, sizeof(body), bytes, deadline);
        if (result != 0) return result;
        if (reply.type != message_type::hello_reply || bytes != sizeof(body) ||
            body.server_version != protocol_version || body.capabilities != 0 || body.reserved != 0 ||
            body.screen_width != 800 || body.screen_height != 600 || reply.session == 0 ||
            body.session_epoch != reply.session) return fail(process_error_invalid);
        session_ = reply.session;
        return 0;
    }

    i64 status(message_type type, u64 object, const void* payload, u32 size, u64 deadline,
               const void* pixels = nullptr, u32 pixel_bytes = 0, u64* created = nullptr) {
        status_payload body{}; wire_header reply{}; u32 bytes = 0;
        const i64 result = exchange(type, object, payload, size, pixels, pixel_bytes, reply,
                                    &body, sizeof(body), bytes, deadline);
        if (result != 0) return result;
        if (reply.type != message_type::ack || bytes != sizeof(body)) return fail(process_error_invalid);
        if (created && body.result == 0) {
            if (reply.object == 0) return fail(process_error_invalid);
            *created = reply.object;
        }
        return body.result;
    }
    i64 create(const create_window_payload& request, u64& object, u64 deadline) {
        object = 0;
        return status(message_type::create_window, 0, &request, sizeof(request), deadline, nullptr, 0, &object);
    }
    i64 configure(u64 object, const configure_payload& request, u64 deadline) {
        return status(message_type::configure, object, &request, sizeof(request), deadline);
    }
    i64 begin(u64 object, const frame_payload& request, u64 deadline) {
        return status(message_type::begin_frame, object, &request, sizeof(request), deadline);
    }
    i64 tile(u64 object, const tile_payload& request, const void* pixels, u32 size, u64 deadline) {
        return status(message_type::write_tile, object, &request, sizeof(request), deadline, pixels, size);
    }
    i64 commit(u64 object, u64 serial, u64 deadline) {
        const commit_payload request{serial, 0, 0};
        return status(message_type::commit_frame, object, &request, sizeof(request), deadline);
    }
    i64 input(u64 object, input_payload& event, u64 deadline) {
        wire_header reply{}; u8 body[sizeof(input_payload)]{}; u32 bytes = 0;
        const i64 result = exchange(message_type::input, object, nullptr, 0, nullptr, 0,
                                    reply, body, sizeof(body), bytes, deadline);
        if (result != 0) return result;
        if (reply.type == message_type::ack && bytes == sizeof(status_payload)) {
            status_payload value{}; copy(&value, body, sizeof(value)); return value.result;
        }
        if (reply.type != message_type::input || bytes != sizeof(event)) return fail(process_error_invalid);
        copy(&event, body, sizeof(event)); return 0;
    }
};

} // namespace xos::interactium
