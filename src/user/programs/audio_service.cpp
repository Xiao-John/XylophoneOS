// SPDX-License-Identifier: Apache-2.0
#include <xos/audio_abi.hpp>
#include <xos/channel_io.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

namespace {
using namespace xos;
using namespace xos::audio;
struct session {
    bool used;
    ipc_channel channel;
    u64 peer_pid, job_id;
    job_state state;
    u32 completed_notes;
    i64 result;
};
struct playback {
    bool active;
    u32 session_index, note_count, note_index;
    u64 job_id, worker_pid, rest_deadline_ns;
    note notes[max_notes];
};
session sessions[max_sessions];
session overflow_session{};
playback current_job{};
u64 next_job_id = 1;
u32 tone_image;

i64 monotonic_now(u64& value) {
    const i64 result = sdk::syscall(sys_clock_monotonic);
    if (result < 0) return result;
    value = static_cast<u64>(result);
    return 0;
}

// Closing an endpoint revokes the mailbox together with an unread reply, so
// a teardown waits (bounded) until the peer drains the reply first.
constexpr u64 reply_drain_ns = 4 * thread_tick_ns;

bool wait_reply_consumed(const session& item) {
    if (item.channel.send == 0) return false;
    u64 now = 0;
    if (monotonic_now(now) != 0 || now > thread_deadline_infinite - reply_drain_ns) return false;
    const u64 deadline = now + reply_drain_ns;
    for (;;) {
        // try_send reports 0 once the reply was read, would_block while it
        // is still queued, and a fatal error once the endpoint is gone.
        const i64 ready = sdk::ipc_wait(item.channel.send, ipc_wait_mode::try_send);
        if (ready != process_error_would_block) return ready == 0;
        if (monotonic_now(now) != 0 || now >= deadline) return false;
        const u64 next = now + thread_tick_ns;
        (void)sdk::syscall(sys_sleep_until, next < deadline ? next : deadline);
    }
}

void close_session(session& item) {
    if (item.channel.send != 0) (void)sdk::ipc_channel_close(item.channel.send);
    if (item.channel.receive != 0) (void)sdk::ipc_channel_close(item.channel.receive);
    item = {};
}

bool send_response(session& item, job_state state, i64 result = 0, u64 job_id = 0,
                   u32 completed = 0) {
    response reply{};
    reply.version = protocol_version;
    reply.size = sizeof(reply);
    reply.state = static_cast<u32>(state);
    reply.completed_notes = completed;
    reply.result = result;
    reply.job_id = job_id;
    reply.max_notes = max_notes;
    reply.max_sequence_ms = max_sequence_ms;
    reply.min_frequency_hz = min_frequency_hz;
    reply.max_frequency_hz = max_frequency_hz;
    // ipc_send reports success as 0; a full mailbox only means the previous
    // reply is still unread, so wait for the peer and retry once.
    i64 sent = sdk::ipc_send(item.channel.send, &reply, sizeof(reply));
    if (sent == sdk::ipc_error_full && wait_reply_consumed(item)) {
        sent = sdk::ipc_send(item.channel.send, &reply, sizeof(reply));
    }
    return sent == 0;
}

bool unused_notes_are_zero(const request& message, u32 first) {
    for (u32 i = first; i < max_notes; ++i) {
        if (message.notes[i].frequency_hz != 0 || message.notes[i].duration_ms != 0) return false;
    }
    return true;
}

void reap_worker() {
    if (!current_job.active || current_job.worker_pid == 0) return;
    process_status status{};
    const i64 result = sdk::syscall(sys_process_wait, current_job.worker_pid,
                                    reinterpret_cast<u64>(&status), 1);
    if (result == process_error_would_block) return;
    session& owner = sessions[current_job.session_index];
    current_job.worker_pid = 0;
    if (result != 0 || status.outcome != process_outcome::exited || status.code != 0) {
        if (owner.used && owner.job_id == current_job.job_id) {
            owner.state = result == 0 && status.outcome == process_outcome::exited && status.code == 6
                ? job_state::expired : job_state::device_lost;
            owner.result = result == 0 ? static_cast<i64>(status.code) : result;
        }
        current_job.active = false;
        return;
    }
    if (owner.used && owner.job_id == current_job.job_id) ++owner.completed_notes;
    ++current_job.note_index;
}

void cancel_current_job(job_state final_state, i64 result) {
    if (!current_job.active) return;
    if (current_job.worker_pid != 0) reap_worker();
    if (!current_job.active) return;
    if (current_job.active && current_job.note_index == current_job.note_count) {
        session& finished = sessions[current_job.session_index];
        if (finished.used && finished.job_id == current_job.job_id) {
            finished.state = job_state::completed; finished.result = 0;
        }
        current_job.active = false;
        return;
    }
    if (current_job.worker_pid != 0) {
        const i64 cancelled = sdk::syscall(sys_process_cancel, current_job.worker_pid);
        if (cancelled == 0) {
            process_status status{};
            (void)sdk::syscall(sys_process_wait, current_job.worker_pid,
                               reinterpret_cast<u64>(&status), 1);
        }
        current_job.worker_pid = 0;
    }
    session& owner = sessions[current_job.session_index];
    if (owner.used && owner.job_id == current_job.job_id) {
        owner.state = final_state;
        owner.result = result;
    }
    current_job.active = false;
}

void disconnect_session(session& item, bool overflow) {
    if (!overflow && current_job.active && &item == &sessions[current_job.session_index])
        cancel_current_job(job_state::cancelled, pipe_error_broken);
    close_session(item);
}

u32 free_session_slot() {
    for (u32 i = 0; i < max_sessions; ++i) if (!sessions[i].used) return i;
    return max_sessions;
}

void accept_connection() {
    ipc_channel channel{};
    const i64 accepted = sdk::ipc_name_try_accept(channel);
    if (accepted == process_error_would_block) return;
    if (accepted != 0) return;
    session* target = nullptr;
    const u32 slot = free_session_slot();
    if (slot < max_sessions) target = &sessions[slot];
    else if (!overflow_session.used) target = &overflow_session;
    if (target == nullptr) {
        (void)sdk::ipc_channel_close(channel.send);
        (void)sdk::ipc_channel_close(channel.receive);
        return;
    }
    u64 peer = 0;
    if (sdk::ipc_endpoint_peer(channel.receive, peer) != 0 || peer == 0) {
        (void)sdk::ipc_channel_close(channel.send);
        (void)sdk::ipc_channel_close(channel.receive);
        return;
    }
    for (const auto& existing : sessions) {
        if (existing.used && existing.peer_pid == peer) {
            if (!overflow_session.used) target = &overflow_session;
            else {
                (void)sdk::ipc_channel_close(channel.send);
                (void)sdk::ipc_channel_close(channel.receive);
                return;
            }
            break;
        }
    }
    target->used = true;
    target->channel = channel;
    target->peer_pid = peer;
    target->state = job_state::none;
}

void handle_request(session& item, bool overflow) {
    request message{};
    const i64 received = sdk::ipc_recv(item.channel.receive, &message, sizeof(message));
    if (received == sdk::ipc_error_empty) return;
    if (received < 0) { disconnect_session(item, overflow); return; }
    response reply{};
    reply.version = protocol_version;
    reply.size = sizeof(reply);
    reply.state = static_cast<u32>(job_state::none);
    reply.max_notes = max_notes;
    reply.max_sequence_ms = max_sequence_ms;
    reply.min_frequency_hz = min_frequency_hz;
    reply.max_frequency_hz = max_frequency_hz;
    auto respond = [&]() {
        // Only an unreachable peer (or one that never drains its mailbox)
        // ends the session; a successfully queued reply keeps it.
        if (!send_response(item, static_cast<job_state>(reply.state), reply.result,
                           reply.job_id, reply.completed_notes)) disconnect_session(item, overflow);
    };
    if (received != static_cast<i64>(sizeof(message)) || message.version != protocol_version ||
        message.size != sizeof(message) || message.reserved != 0) {
        reply.result = process_error_invalid; respond(); return;
    }
    const auto operation_value = static_cast<operation>(message.operation);
    if (overflow) {
        reply.result = process_error_busy;
        respond();
        if (item.used) {
            wait_reply_consumed(item); // closing would revoke an unread reply
            close_session(item);
        }
        return;
    }
    if (operation_value == operation::capabilities) {
        if (message.note_count != 0 || message.job_id != 0 || !unused_notes_are_zero(message, 0)) {
            reply.result = process_error_invalid;
        }
        respond(); return;
    }
    if (operation_value == operation::submit) {
        reply.result = validate_sequence(message.notes, message.note_count);
        if (reply.result != 0 || message.job_id != 0 ||
            !unused_notes_are_zero(message, message.note_count)) {
            if (reply.result == 0) reply.result = process_error_invalid;
            respond(); return;
        }
        if (current_job.active || item.state == job_state::accepted || item.state == job_state::playing) {
            reply.result = process_error_busy; respond(); return;
        }
        if (next_job_id == 0 || next_job_id == ~u64{0}) {
            reply.result = process_error_resources; respond(); return;
        }
        item.job_id = next_job_id++;
        item.state = job_state::accepted;
        item.result = 0;
        item.completed_notes = 0;
        current_job = {};
        current_job.active = true;
        current_job.session_index = static_cast<u32>(&item - sessions);
        current_job.job_id = item.job_id;
        current_job.note_count = message.note_count;
        for (u32 i = 0; i < message.note_count; ++i) current_job.notes[i] = message.notes[i];
        reply.result = 0;
        reply.state = static_cast<u32>(job_state::accepted);
        reply.job_id = item.job_id;
        respond(); return;
    }
    if (operation_value == operation::status || operation_value == operation::cancel) {
        if (message.note_count != 0 || !unused_notes_are_zero(message, 0) || message.job_id == 0 ||
            message.job_id != item.job_id) {
            reply.result = process_error_invalid; respond(); return;
        }
        if (operation_value == operation::cancel && current_job.active &&
            current_job.session_index == static_cast<u32>(&item - sessions) &&
            current_job.job_id == message.job_id) cancel_current_job(job_state::cancelled, 0);
        reply.state = static_cast<u32>(item.state);
        reply.result = item.result;
        reply.job_id = item.job_id;
        reply.completed_notes = item.completed_notes;
        respond(); return;
    }
    if (operation_value == operation::close) {
        if (message.note_count != 0 || message.job_id != 0 || !unused_notes_are_zero(message, 0)) {
            reply.result = process_error_invalid; respond(); return;
        }
        if (current_job.active && current_job.session_index == static_cast<u32>(&item - sessions))
            cancel_current_job(job_state::cancelled, pipe_error_broken);
        reply.result = 0;
        respond();
        if (item.used) {
            wait_reply_consumed(item); // closing would revoke an unread reply
            close_session(item);
        }
        return;
    }
    reply.result = process_error_invalid;
    respond();
}

i64 prepare_tone_worker(u64 child, void*) {
    return sdk::pio_grant(pio_grant_action::grant, child, pio_resource_pc_speaker);
}

bool start_tone_worker(u32 frequency, u32 duration_ms, u64& child_pid) {
    char frequency_text[11]{}, duration_text[11]{};
    auto decimal = [](u32 value, char* output) {
        char reverse[10]; u32 length = 0;
        do { reverse[length++] = static_cast<char>('0' + value % 10); value /= 10; } while (value != 0);
        for (u32 i = 0; i < length; ++i) output[i] = reverse[length - i - 1];
        output[length] = '\0';
    };
    decimal(frequency, frequency_text); decimal(duration_ms, duration_text);
    const char* argv[] = {"audio_tone", frequency_text, duration_text};
    sdk::spawn_options options{};
    for (u32 i = 0; i < 3; ++i) options.stdio[i] = -2;
    options.prepare_child = prepare_tone_worker;
    const i64 result = sdk::spawn_image_options(tone_image, 3, argv, options);
    if (result <= 0) return false;
    child_pid = static_cast<u64>(result);
    return true;
}

void advance_playback() {
    if (!current_job.active || current_job.worker_pid != 0) return;
    session& owner = sessions[current_job.session_index];
    if (!owner.used || owner.job_id != current_job.job_id) {
        cancel_current_job(job_state::cancelled, pipe_error_broken); return;
    }
    if (current_job.note_index == current_job.note_count) {
        owner.state = job_state::completed;
        owner.result = 0;
        current_job.active = false;
        return;
    }
    const note& item = current_job.notes[current_job.note_index];
    u64 now = 0;
    if (monotonic_now(now) != 0) {
        owner.state = job_state::device_lost; owner.result = process_error_state;
        current_job.active = false; return;
    }
    if (item.frequency_hz == 0) {
        if (current_job.rest_deadline_ns == 0) {
            const u64 duration = static_cast<u64>(item.duration_ms) * 1000000ull;
            if (now > thread_deadline_infinite - duration) {
                owner.state = job_state::expired; owner.result = thread_error_timeout;
                current_job.active = false; return;
            }
            current_job.rest_deadline_ns = now + duration;
            owner.state = job_state::playing;
            return;
        }
        if (now < current_job.rest_deadline_ns) return;
        current_job.rest_deadline_ns = 0;
        ++current_job.note_index;
        ++owner.completed_notes;
        return;
    }
    u64 child = 0;
    if (!start_tone_worker(item.frequency_hz, item.duration_ms, child)) {
        owner.state = job_state::device_lost;
        owner.result = process_error_resources;
        current_job.active = false;
        return;
    }
    current_job.worker_pid = child;
    owner.state = job_state::playing;
}

void sleep_one_tick() {
    u64 now = 0;
    if (monotonic_now(now) != 0 || now > thread_deadline_infinite - thread_tick_ns) {
        sdk::yield(); return;
    }
    (void)sdk::syscall(sys_sleep_until, now + thread_tick_ns);
}
}

extern "C" int xos_user_main(const xos::startup_info*) {
    using namespace xos;
    using namespace xos::audio;
    for (u32 id = 1; id < 32; ++id) {
        image_info info{};
        if (sdk::syscall(sys_image_info, id, reinterpret_cast<u64>(&info)) < 0) break;
        if (sdk::equal(info.name, "audio_tone")) { tone_image = id; break; }
    }
    if (tone_image == 0 || sdk::ipc_name_publish(service_name) != 0) return 10;
    for (;;) {
        reap_worker();
        advance_playback();
        accept_connection();
        for (auto& item : sessions) if (item.used) handle_request(item, false);
        if (overflow_session.used) handle_request(overflow_session, true);
        sleep_one_tick();
    }
}
