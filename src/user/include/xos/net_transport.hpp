// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/net_service_client.hpp>

namespace xos::net2 {
inline bool parse_ipv4(const char* text, u32& address) {
    address = 0;
    if (!text) return false;
    for (u32 part = 0; part < 4; ++part) {
        u32 value = 0, digits = 0; const bool leading_zero = *text == '0';
        while (*text >= '0' && *text <= '9') {
            if (++digits > 3) return false;
            value = value * 10 + static_cast<u32>(*text++ - '0');
        }
        if (!digits || value > 255 || (leading_zero && digits > 1)) return false;
        address = (address << 8) | value;
        if (part < 3) { if (*text++ != '.') return false; }
        else if (*text) return false;
    }
    return true;
}
inline const char* error_name(i64 result) {
    switch (result) {
    case 0: return "ok"; case invalid: return "invalid"; case denied: return "denied";
    case resources: return "resources"; case would_block: return "would_block"; case timeout: return "timeout";
    case closed: return "closed"; case io: return "io"; case unsupported: return "unsupported";
    case buffer_too_small: return "buffer_too_small"; case reset: return "reset";
    default: return "transport_error";
    }
}
class client {
public:
    i64 connect(u64 expected_service_pid) { return session_.connect(expected_service_pid); }
    void close() { session_.close(); }
    i64 open(protocol transport, u32 address, u16 port, u64 deadline, u64& handle) {
        handle = 0;
        if ((transport != protocol::tcp && transport != protocol::udp) || !port) return invalid;
        message request{}, reply{}; request.action = operation::open; request.transport = transport;
        request.address = address; request.port = port; request.deadline = deadline;
        i64 result = session_.request(request, reply);
        if (result) return result;
        const u64 candidate = reply.object;
        for (;;) {
            if ((reply.flags & ~(connecting | connected | eof)) ||
                ((reply.flags & connecting) && (reply.flags & (connected | eof)))) { close(); return io; }
            if (reply.flags & connected) { handle = candidate; return 0; }
            if (reply.flags != connecting) { close(); return io; }
            result = pause(deadline);
            if (result) { close(); return result; }
            request = {}; request.action = operation::status; request.object = candidate; request.deadline = deadline;
            result = session_.request(request, reply);
            if (result) {
                (void)cancel_connection(candidate, deadline); return result;
            }
        }
    }
    // TCP stream operations return a short count. Retry only a confirmed
    // would_block response; an IPC timeout closes the session without replay.
    i64 write(u64 handle, const u8* data, u32 length, u64 deadline) {
        if (!handle || (length && !data)) return invalid;
        if (!length) return 0;
        const i64 result = send_once(handle, data, length < payload_bytes ? length : payload_bytes, deadline);
        if (!result) { close(); return io; }
        return result;
    }
    i64 read(u64 handle, u8* data, u32 capacity, u64 deadline) {
        if (!handle || (capacity && !data)) return invalid;
        if (!capacity) return 0;
        u32 required = 0;
        return receive_once(handle, data, capacity < payload_bytes ? capacity : payload_bytes, deadline, required, false);
    }
    i64 send_datagram(u64 handle, const u8* data, u32 length, u64 deadline) {
        if (!handle || length > payload_bytes || (length && !data)) return invalid;
        const i64 result = send_once(handle, data, length, deadline);
        if (result >= 0 && result != static_cast<i64>(length)) { close(); return io; }
        return result;
    }
    i64 receive_datagram(u64 handle, u8* data, u32 capacity, u64 deadline, u32& required) {
        required = 0;
        if (!handle || !data || !capacity) return invalid;
        return receive_once(handle, data, capacity < payload_bytes ? capacity : payload_bytes, deadline, required, true);
    }
    i64 close_connection(u64 handle, u64 deadline) { return finish(handle, deadline, false); }
    i64 cancel_connection(u64 handle, u64 deadline) { return finish(handle, deadline, true); }
private:
    session_client session_;
    i64 pause(u64 deadline) {
        const i64 value = sdk::syscall(sys_clock_monotonic);
        if (value < 0) return io;
        const u64 now = static_cast<u64>(value);
        if (now >= deadline) return timeout;
        return sdk::syscall(sys_sleep_until, deadline - now < thread_tick_ns ? deadline : now + thread_tick_ns) ? io : 0;
    }
    i64 exchange(message& request, message& reply) {
        for (;;) {
            const i64 result = session_.request(request, reply);
            if (result != would_block) return result;
            const i64 waited = pause(request.deadline);
            if (waited) { close(); return waited; }
        }
    }
    i64 send_once(u64 handle, const u8* data, u32 length, u64 deadline) {
        message request{}, reply{}; request.action = operation::send; request.object = handle;
        request.deadline = deadline; request.length = length;
        for (u32 i = 0; i < length; ++i) request.data[i] = data[i];
        return exchange(request, reply);
    }
    i64 receive_once(u64 handle, u8* data, u32 capacity, u64 deadline, u32& required, bool datagram) {
        message request{}, reply{}; request.action = operation::receive; request.object = handle;
        request.deadline = deadline; request.flags = capacity;
        const i64 result = exchange(request, reply);
        if (result == buffer_too_small) {
            if (!datagram || reply.flags <= capacity || reply.flags > payload_bytes) { close(); return io; }
            required = reply.flags; return result;
        }
        if (result) return result;
        if (reply.length > capacity || (reply.flags & ~eof) ||
            (datagram && reply.flags) || (!datagram && !reply.length && !(reply.flags & eof))) { close(); return io; }
        for (u32 i = 0; i < reply.length; ++i) data[i] = reply.data[i];
        required = reply.length; return reply.length;
    }
    i64 finish(u64 handle, u64 deadline, bool cancel) {
        if (!handle) return invalid;
        message request{}, reply{}; request.action = cancel ? operation::cancel : operation::close;
        request.object = handle; request.deadline = deadline;
        // A confirmed orderly-close refusal can require the caller to drain
        // unread data. Return it without waiting or dropping sibling handles.
        return cancel ? exchange(request, reply) : session_.request(request, reply);
    }
};
}
