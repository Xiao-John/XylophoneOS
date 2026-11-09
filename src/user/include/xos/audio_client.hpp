// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/audio_abi.hpp>
#include <xos/channel_io.hpp>
#include <xos/thread_abi.hpp>

namespace xos::audio {
class client {
    ipc_channel channel_{};
    bool open_ = false;

    void invalidate() {
        if (channel_.send != 0) (void)sdk::ipc_channel_close(channel_.send);
        if (channel_.receive != 0) (void)sdk::ipc_channel_close(channel_.receive);
        channel_ = {};
        open_ = false;
    }
    i64 exchange(request& message, response& reply) {
        if (!open_) return process_error_state;
        const i64 now_value = sdk::syscall(sys_clock_monotonic);
        if (now_value < 0 || static_cast<u64>(now_value) >
                             thread_deadline_infinite - 1000000000ull) {
            invalidate(); return now_value < 0 ? now_value : thread_error_timeout;
        }
        const u64 deadline = static_cast<u64>(now_value) + 1000000000ull;
        const i64 sent = sdk::channel_send_wait(channel_.send, &message, sizeof(message),
                                                deadline);
        if (sent != 0) { invalidate(); return sent; }
        const i64 received = sdk::channel_receive_wait(channel_.receive, &reply, sizeof(reply),
                                                      deadline);
        if (received != static_cast<i64>(sizeof(reply))) {
            invalidate(); return received < 0 ? received : process_error_state;
        }
        if (reply.version != protocol_version || reply.size != sizeof(reply) ||
            reply.state > static_cast<u32>(job_state::device_lost)) {
            invalidate(); return process_error_state;
        }
        return 0;
    }
public:
    client() = default;
    client(const client&) = delete;
    client& operator=(const client&) = delete;

    i64 connect() {
        if (open_) return process_error_state;
        const i64 connected = sdk::ipc_name_connect(service_name, channel_);
        if (connected != 0) { channel_ = {}; return connected; }
        open_ = true;
        request message{}; response reply{};
        message.operation = static_cast<u32>(operation::capabilities);
        const i64 result = exchange(message, reply);
        if (result != 0) { invalidate(); return result; }
        if (reply.result != 0) { invalidate(); return reply.result; }
        if (reply.max_notes != max_notes ||
            reply.max_sequence_ms != max_sequence_ms ||
            reply.min_frequency_hz != min_frequency_hz ||
            reply.max_frequency_hz != max_frequency_hz) {
            invalidate();
            return process_error_state;
        }
        return 0;
    }
    i64 submit(const note* notes, u32 count, u64& job_id) {
        job_id = 0;
        const i64 valid = validate_sequence(notes, count);
        if (valid != 0) return valid;
        request message{}; response reply{};
        message.operation = static_cast<u32>(operation::submit);
        message.note_count = count;
        for (u32 i = 0; i < count; ++i) message.notes[i] = notes[i];
        const i64 transport = exchange(message, reply);
        if (transport != 0) return transport;
        if (reply.result == 0 && (reply.job_id == 0 || reply.state != static_cast<u32>(job_state::accepted))) {
            invalidate(); return process_error_state;
        }
        if (reply.result == 0) job_id = reply.job_id;
        return reply.result;
    }
    i64 status(u64 job_id, response& output) {
        request message{}; message.operation = static_cast<u32>(operation::status);
        message.job_id = job_id;
        const i64 result = exchange(message, output);
        return result != 0 ? result : output.result;
    }
    i64 cancel(u64 job_id, response& output) {
        request message{}; message.operation = static_cast<u32>(operation::cancel);
        message.job_id = job_id;
        const i64 result = exchange(message, output);
        return result != 0 ? result : output.result;
    }
    i64 close() {
        if (!open_) return 0;
        request message{}; response reply{};
        message.operation = static_cast<u32>(operation::close);
        const i64 result = exchange(message, reply);
        invalidate();
        return result != 0 ? result : reply.result;
    }
    bool connected() const { return open_; }
};
}
