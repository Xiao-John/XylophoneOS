// SPDX-License-Identifier: Apache-2.0
#include <xos/launch_control.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

namespace xos::launch {
namespace {
constexpr u32 registry_limit = 16, enumeration_limit = 128;
constexpr u64 poll_interval_ns = 10'000'000;
constexpr i64 ipc_empty = -3, ipc_full = -4;
enum class after_send : u8 { none, activate, fail, cancel };
struct child_record {
    u64 pid = 0, issued_generation = 0, last_nonce = 0;
    descriptor active{}, pending{}, retired{};
    artifact active_artifact{}, pending_artifact{}, retired_artifact{};
    admission_check check = nullptr;
    void* check_context = nullptr;
    message outgoing{};
    diagnostic latest{};
    process_status terminal{};
    bool active_valid = false, pending_valid = false, channels_open = false, retired_valid = false;
    bool has_outgoing = false, terminal_cached = false, delivered = false;
    after_send after = after_send::none;
};
child_record children[registry_limit]{};
u64 registry_pid = 0;
u64 registry_lock = 0;

struct guard {
    bool acquired;
    guard() : acquired(false) {
        const u64 self = sdk::pid();
        u64 expected = __atomic_load_n(&registry_lock, __ATOMIC_RELAXED);
        // A fork can copy this lock while a parent thread owns it. Only that
        // different PID's private copy may be taken over; same-PID threads
        // continue to contend normally without an unsynchronized reset.
        if (expected != self)
            acquired = __atomic_compare_exchange_n(&registry_lock, &expected, self, false,
                                                   __ATOMIC_ACQUIRE, __ATOMIC_RELAXED);
        if (acquired && registry_pid != self) {
            for (auto& item : children) item = {};
            registry_pid = self;
        }
    }
    ~guard() { release(); }
    void release() {
        if (acquired) { acquired = false; __atomic_store_n(&registry_lock, 0, __ATOMIC_RELEASE); }
    }
};

i64 clock_now(u64& now) {
    const i64 result = sdk::syscall(sys_clock_monotonic);
    if (result < 0) return result;
    now = static_cast<u64>(result);
    return 0;
}
i64 finite_deadline(u64 now, u64 deadline) {
    if (!deadline || deadline == ~u64{0}) return process_error_invalid;
    if (deadline <= now) return thread_error_timeout;
    if (deadline - now > XOS_LAUNCH_CONTROL_MAX_NS) return process_error_invalid;
    return 0;
}
bool descriptor_shape(const descriptor& value) {
    return value.magic == XOS_LAUNCH_CONTROL_MAGIC && value.version == XOS_LAUNCH_CONTROL_VERSION &&
           value.size == sizeof(value) && value.controller_pid && value.child_pid &&
           value.controller_pid != value.child_pid && value.generation && value.nonce && value.deadline &&
           value.deadline != ~u64{0} && value.ready_handle && value.ack_handle &&
           value.ready_handle != value.ack_handle && !value.reserved[0] && !value.reserved[1];
}
i64 authenticate_child(const descriptor& value) {
    if (!descriptor_shape(value)) return process_error_invalid;
    if (value.child_pid != sdk::pid()) return process_error_denied;
    bool ready = false, ack = false;
    for (u32 index = 0; index < enumeration_limit; ++index) {
        channel_info info{};
        const i64 result = sdk::channel_get(index, info);
        if (result == thread_error_not_found) break;
        if (result != 0) return result;
        if (info.handle != value.ready_handle && info.handle != value.ack_handle) continue;
        if (info.version != channel_version || info.size != sizeof(info) ||
            info.peer_pid != value.controller_pid || info.controller_pid != value.controller_pid)
            return process_error_denied;
        if (info.handle == value.ready_handle) {
            if (info.rights != channel_send || ready) return process_error_denied;
            ready = true;
        } else {
            if (info.rights != channel_receive || ack) return process_error_denied;
            ack = true;
        }
        if (ready && ack) return 0;
    }
    return process_error_denied;
}
bool artifact_empty(const artifact& value) {
    if (value.id) return false;
    for (const auto byte : value.sha256) if (byte) return false;
    return true;
}
bool artifact_shape(const artifact& value) {
    bool hash = false;
    for (const auto byte : value.sha256) hash = hash || byte != 0;
    return value.id ? hash : !hash;
}
bool same_artifact(const artifact& left, const artifact& right) {
    if (left.id != right.id) return false;
    for (u32 i = 0; i < sizeof(left.sha256); ++i) if (left.sha256[i] != right.sha256[i]) return false;
    return true;
}
message make_message(const descriptor& value, const artifact& admitted, u32 type,
                     i64 status = 0, u32 phase = 0, u64 deadline = 0) {
    return {XOS_LAUNCH_CONTROL_MAGIC, XOS_LAUNCH_CONTROL_VERSION, sizeof(message), type, phase,
            value.generation, value.nonce, value.child_pid, deadline ? deadline : value.deadline, status,
            admitted, {0, 0, 0}};
}
bool message_shape(const message& value) {
    return value.magic == XOS_LAUNCH_CONTROL_MAGIC && value.version == XOS_LAUNCH_CONTROL_VERSION &&
           value.size == sizeof(value) && value.generation && value.nonce && value.pid &&
           value.deadline && value.deadline != ~u64{0} && !value.reserved[0] && !value.reserved[1] &&
           !value.reserved[2] && artifact_shape(value.artifact) &&
           value.type >= XOS_LAUNCH_PREPARE && value.type <= XOS_LAUNCH_CANCEL_ACK;
}
bool identity(const message& value, const descriptor& control, bool include_deadline = true) {
    return value.generation == control.generation && value.nonce == control.nonce &&
           value.pid == control.child_pid && (!include_deadline || value.deadline == control.deadline);
}
i64 new_nonce(u64 first, u64 second, u64& output) {
    for (u32 tries = 0; tries < 4; ++tries) {
        u64 value = 0;
        const i64 result = sdk::syscall(sys_random_bytes, reinterpret_cast<u64>(&value), sizeof(value));
        if (result != 0) return result;
        if (value && value != first && value != second) { output = value; return 0; }
    }
    return random_error_io;
}
i64 admit(admission_check check, void* context, u64 child, const artifact& current,
          const artifact& requested, u64 deadline) {
    if (!artifact_shape(requested)) return process_error_invalid;
    if (check == nullptr) return artifact_empty(requested) ? 0 : process_error_denied;
    const i64 result = check(context, child, current, requested, deadline);
    return result <= 0 ? result : process_error_invalid;
}
child_record* find(u64 pid) {
    for (auto& item : children) if (item.pid == pid) return &item;
    return nullptr;
}
const descriptor& channels(const child_record& item) {
    return item.active_valid ? item.active : item.pending;
}
void close_channels(child_record& item) {
    if (item.channels_open) {
        const auto& value = channels(item);
        (void)sdk::channel_close(value.ready_handle);
        (void)sdk::channel_close(value.ack_handle);
        item.channels_open = false;
    }
    item.has_outgoing = false;
    item.after = after_send::none;
}
void protocol_failure(child_record& item, i64 status) {
    const u64 generation = item.pending_valid ? item.pending.generation : item.active.generation;
    // Preserve an acknowledged loader failure after the child's channel close.
    if (item.pending_valid || !item.latest.status)
        item.latest = {status, XOS_LAUNCH_PHASE_NONE, generation,
                       item.pending_valid ? item.pending_artifact : item.active_artifact};
    close_channels(item);
    item.pending_valid = false;
}
void queue(child_record& item, const message& value, after_send after) {
    item.outgoing = value;
    item.after = after;
    item.has_outgoing = true;
}
void flush(child_record& item) {
    if (!item.has_outgoing || !item.channels_open) return;
    const i64 sent = sdk::ipc_send(channels(item).ack_handle, &item.outgoing, sizeof(item.outgoing));
    if (sent == ipc_full) return;
    if (sent != 0) { protocol_failure(item, sent); return; }
    const after_send after = item.after;
    item.has_outgoing = false;
    item.after = after_send::none;
    if (after == after_send::activate) {
        item.active = item.pending;
        item.active_artifact = item.pending_artifact;
        item.active_valid = true;
        item.pending_valid = false;
        item.latest = {0, 0, item.active.generation, item.active_artifact};
    } else if (after == after_send::fail || after == after_send::cancel) {
        item.pending_valid = false;
    }
}
void expire(child_record& item, u64 now) {
    if (!item.pending_valid || now < item.pending.deadline) return;
    item.latest = {thread_error_timeout, XOS_LAUNCH_PHASE_NONE, item.pending.generation, item.pending_artifact};
    // A timed-out precommit candidate does not revoke the valid old image.
    if (!item.active_valid) close_channels(item);
    else { item.retired = item.pending; item.retired_artifact = item.pending_artifact; item.retired_valid = true; }
    item.pending_valid = false;
    item.has_outgoing = false;
    item.after = after_send::none;
}
void cache_terminal(child_record& item, const process_status& status);
void service(child_record& item, u64 now) {
    if (!item.pid || item.delivered || item.terminal_cached || !item.channels_open) return;
    expire(item, now);
    if (!item.channels_open) return;
    flush(item);
    if (!item.channels_open || item.has_outgoing) return;
    message input{};
    const i64 received = sdk::ipc_recv(channels(item).ready_handle, &input, sizeof(input));
    if (received == ipc_empty) return;
    if (received < 0) {
        process_status status{};
        const i64 ended = sdk::syscall(sys_process_wait, item.pid, reinterpret_cast<u64>(&status), process_wait_nonblocking);
        if (ended == 0) {
            const bool unfinished = item.pending_valid;
            cache_terminal(item, status);
            if (unfinished && !item.latest.status)
                item.latest = {process_error_state, XOS_LAUNCH_PHASE_NONE, item.issued_generation, item.pending_artifact};
            return;
        }
    }
    if (received != sizeof(input) || !message_shape(input) || input.pid != item.pid) {
        protocol_failure(item, received < 0 ? received : process_error_invalid);
        return;
    }
    const i64 clock_error = clock_now(now);
    if (clock_error) { protocol_failure(item, clock_error); return; }
    expire(item, now);
    if (!item.channels_open) return;
    if (item.retired_valid && identity(input, item.retired) && same_artifact(input.artifact, item.retired_artifact) &&
        now >= item.retired.deadline)
        return; // Consume late candidates, never acknowledge expired authority.
    if (input.type == XOS_LAUNCH_PREPARE) {
        if (!item.active_valid || item.pending_valid || !identity(input, item.active, false) || input.status || input.phase) {
            protocol_failure(item, process_error_invalid); return;
        }
        u64 nonce = 0;
        i64 error = finite_deadline(now, input.deadline);
        if (!error && item.issued_generation == ~u64{0}) error = process_error_resources;
        if (!error) error = admit(item.check, item.check_context, item.pid, item.active_artifact, input.artifact, input.deadline);
        if (!error) error = clock_now(now);
        if (!error) error = finite_deadline(now, input.deadline);
        if (!error) error = new_nonce(item.active.nonce, item.last_nonce, nonce);
        if (!error) error = clock_now(now);
        if (!error) error = finite_deadline(now, input.deadline);
        if (error) {
            item.latest = {error, XOS_LAUNCH_PHASE_PREPARE, item.active.generation, input.artifact};
            queue(item, make_message(item.active, input.artifact, XOS_LAUNCH_ALLOW, error,
                                     XOS_LAUNCH_PHASE_PREPARE, input.deadline), after_send::none);
        } else {
            item.pending = item.active;
            item.pending.generation = ++item.issued_generation;
            item.pending.nonce = item.last_nonce = nonce;
            item.pending.deadline = input.deadline;
            item.pending_artifact = input.artifact;
            item.pending_valid = true;
            queue(item, make_message(item.pending, item.pending_artifact, XOS_LAUNCH_ALLOW), after_send::none);
        }
    } else if (!item.pending_valid || !identity(input, item.pending) || !same_artifact(input.artifact, item.pending_artifact)) {
        protocol_failure(item, process_error_invalid);
    } else if (input.type == XOS_LAUNCH_READY && !input.status && !input.phase) {
        i64 admission = admit(item.check, item.check_context, item.pid, item.active_artifact,
                              item.pending_artifact, item.pending.deadline);
        if (!admission) admission = clock_now(now);
        if (!admission) admission = finite_deadline(now, item.pending.deadline);
        if (admission) {
            item.latest = {admission, XOS_LAUNCH_PHASE_ENTRY, input.generation, item.pending_artifact};
            queue(item, make_message(item.pending, item.pending_artifact, XOS_LAUNCH_READY_ACK,
                                     admission, XOS_LAUNCH_PHASE_ENTRY), after_send::fail);
        } else {
            queue(item, make_message(item.pending, item.pending_artifact, XOS_LAUNCH_READY_ACK), after_send::activate);
        }
    } else if (input.type == XOS_LAUNCH_FAILURE && input.status < 0 &&
               input.phase >= XOS_LAUNCH_PHASE_PREPARE && input.phase <= XOS_LAUNCH_PHASE_COMMIT) {
        item.latest = {input.status, input.phase, input.generation, item.pending_artifact};
        queue(item, make_message(item.pending, item.pending_artifact, XOS_LAUNCH_FAILURE_ACK, 0, input.phase), after_send::fail);
    } else if (input.type == XOS_LAUNCH_CANCEL && item.active_valid && !input.status && !input.phase) {
        item.latest = {0, XOS_LAUNCH_PHASE_PREPARE, input.generation, item.pending_artifact};
        queue(item, make_message(item.pending, item.pending_artifact, XOS_LAUNCH_CANCEL_ACK), after_send::cancel);
    } else {
        protocol_failure(item, process_error_invalid);
    }
    flush(item);
}
i64 pump(u64& now) {
    const i64 result = clock_now(now);
    if (result != 0) return result;
    for (auto& item : children) service(item, now);
    return 0;
}
void cache_terminal(child_record& item, const process_status& status) {
    close_channels(item);
    item.pending_valid = false;
    item.terminal = status;
    item.terminal_cached = true;
}
void delivered(child_record& item) {
    close_channels(item);
    item.terminal_cached = false;
    item.pending_valid = false;
    item.delivered = true;
}
void wait_set(channel_wait_many_request& request, u64 now, u64& deadline) {
    request = {channel_version, sizeof(request), 0, 0, {}};
    deadline = now <= ~u64{0} - poll_interval_ns ? now + poll_interval_ns : ~u64{0} - 1;
    for (const auto& item : children) {
        if (!item.channels_open || item.delivered || item.terminal_cached) continue;
        if (item.pending_valid && item.pending.deadline < deadline) deadline = item.pending.deadline;
        if (request.count < channel_wait_many_max)
            request.handles[request.count++] = item.has_outgoing ? channels(item).ack_handle : channels(item).ready_handle;
    }
}
void pause(const channel_wait_many_request& request, u64 deadline) {
    // Closure/timeout are rechecked through the authoritative data operation.
    if (request.count) (void)sdk::channel_wait_many(request, deadline);
    else (void)sdk::syscall(sys_sleep_until, deadline);
}
i64 exchange(const descriptor& control, const message& outgoing, message& incoming) {
    u64 now = 0;
    i64 error = clock_now(now);
    if (error) return error;
    error = finite_deadline(now, outgoing.deadline);
    if (error) return error;
    error = authenticate_child(control);
    if (error) return error;
    for (;;) {
        error = clock_now(now);
        if (error) return error;
        if (now >= outgoing.deadline) return thread_error_timeout;
        const i64 sent = sdk::ipc_send(control.ready_handle, &outgoing, sizeof(outgoing));
        if (sent == 0) break;
        if (sent != ipc_full) return sent;
        error = sdk::channel_wait(control.ready_handle, outgoing.deadline);
        if (error != 0) return error;
    }
    for (;;) {
        error = clock_now(now);
        if (error) return error;
        if (now >= outgoing.deadline) return thread_error_timeout;
        const i64 received = sdk::ipc_recv(control.ack_handle, &incoming, sizeof(incoming));
        if (received == sizeof(incoming)) {
            error = clock_now(now);
            if (error) return error;
            if (now >= outgoing.deadline) return thread_error_timeout;
            if (!message_shape(incoming)) return process_error_invalid;
            // Only a new PREPARE may drain expired replies from its same
            // authenticated controller. Never accept them as current authority,
            // and never replay a request whose delivery outcome is unknown.
            const bool response = incoming.type == XOS_LAUNCH_ALLOW || incoming.type == XOS_LAUNCH_READY_ACK ||
                                  incoming.type == XOS_LAUNCH_FAILURE_ACK || incoming.type == XOS_LAUNCH_CANCEL_ACK;
            const bool earlier_identity = (incoming.generation == control.generation && incoming.nonce == control.nonce) ||
                                          (incoming.generation > control.generation && incoming.nonce != control.nonce);
            if (outgoing.type == XOS_LAUNCH_PREPARE && response && earlier_identity &&
                incoming.pid == control.child_pid && incoming.deadline < outgoing.deadline && incoming.deadline <= now)
                continue;
            return 0;
        }
        if (received != ipc_empty) return received < 0 ? received : process_error_invalid;
        error = sdk::channel_wait(control.ack_handle, outgoing.deadline);
        if (error != 0) return error;
    }
}
}

i64 record_child(u64 child, u64 absolute_deadline, descriptor& output,
                 const artifact& initial, admission_check check, void* context,
                 bool extended_channels) {
    guard held;
    if (!held.acquired) return thread_error_busy;
    u64 now = 0;
    i64 error = clock_now(now);
    if (error) return error;
    error = finite_deadline(now, absolute_deadline);
    if (error) return error;
    if (!child || child == registry_pid || find(child)) return process_error_invalid;
    child_record* slot = nullptr;
    for (auto& item : children) if (!item.pid || item.delivered) { slot = &item; break; }
    if (slot == nullptr) return process_error_resources;
    error = admit(check, context, child, {}, initial, absolute_deadline);
    if (error) return error;
    error = clock_now(now);
    if (error) return error;
    error = finite_deadline(now, absolute_deadline);
    if (error) return error;
    u64 nonce = 0;
    error = new_nonce(0, 0, nonce);
    if (error) return error;
    const channel_create ready{channel_version, sizeof(channel_create), child, registry_pid, sizeof(message), 0};
    const i64 ready_handle = extended_channels ? sdk::channel_open_extended(ready) : sdk::channel_open(ready);
    if (ready_handle < 0) return ready_handle;
    const channel_create ack{channel_version, sizeof(channel_create), registry_pid, child, sizeof(message), 0};
    const i64 ack_handle = extended_channels ? sdk::channel_open_extended(ack) : sdk::channel_open(ack);
    if (ack_handle < 0) { (void)sdk::channel_close(static_cast<u32>(ready_handle)); return ack_handle; }
    error = clock_now(now);
    if (!error) error = finite_deadline(now, absolute_deadline);
    if (error) {
        (void)sdk::channel_close(static_cast<u32>(ready_handle));
        (void)sdk::channel_close(static_cast<u32>(ack_handle));
        return error;
    }
    const descriptor value{XOS_LAUNCH_CONTROL_MAGIC, XOS_LAUNCH_CONTROL_VERSION, sizeof(descriptor),
                           registry_pid, child, 1, nonce, absolute_deadline,
                           static_cast<u32>(ready_handle), static_cast<u32>(ack_handle), {0, 0}};
    *slot = {};
    slot->pid = child;
    slot->issued_generation = 1;
    slot->last_nonce = nonce;
    slot->pending = value;
    slot->pending_artifact = initial;
    slot->check = check;
    slot->check_context = context;
    slot->pending_valid = true;
    slot->channels_open = true;
    output = value;
    return 0;
}

i64 await_ready(u64 child, diagnostic& output) {
    for (;;) {
        channel_wait_many_request request{};
        u64 deadline = 0;
        {
            guard held;
            if (!held.acquired) return thread_error_busy;
            child_record* item = find(child);
            if (item == nullptr || item->delivered) return process_error_denied;
            u64 now = 0;
            const i64 pumped = pump(now);
            if (pumped) return pumped;
            if (item->active_valid) { output = item->latest; return 0; }
            if (!item->pending_valid && !item->has_outgoing) {
                output = item->latest;
                return item->latest.status ? item->latest.status : process_error_state;
            }
            process_status status{};
            const i64 result = sdk::syscall(sys_process_wait, child, reinterpret_cast<u64>(&status), process_wait_nonblocking);
            if (result == 0) {
                cache_terminal(*item, status);
                if (!item->latest.status) item->latest = {process_error_state, 0, item->issued_generation, item->pending_artifact};
                output = item->latest;
                return item->latest.status;
            }
            if (result != process_error_would_block) { output = {result, 0, item->issued_generation, item->pending_artifact}; return result; }
            wait_set(request, now, deadline);
        }
        pause(request, deadline);
    }
}

i64 close_control(u64 child) {
    guard held;
    if (!held.acquired) return thread_error_busy;
    child_record* item = find(child);
    if (item == nullptr) return process_error_denied;
    close_channels(*item);
    if (!item->terminal_cached) *item = {};
    else item->pending_valid = false;
    return 0;
}

i64 last_diagnostic(u64 child, diagnostic& output) {
    guard held;
    if (!held.acquired) return thread_error_busy;
    const child_record* item = find(child);
    if (item == nullptr) return thread_error_not_found;
    output = item->latest;
    return 0;
}

i64 poll() {
    guard held;
    if (!held.acquired) return thread_error_busy;
    u64 now = 0;
    return pump(now);
}

i64 wait(u64 child, process_status& output, u32 flags) {
    if (flags & ~(process_wait_nonblocking | process_wait_any)) return process_error_invalid;
    const bool any = (flags & process_wait_any) != 0, nonblocking = (flags & process_wait_nonblocking) != 0;
    if ((any && child) || (!any && !child)) return process_error_invalid;
    for (;;) {
        channel_wait_many_request request{};
        u64 deadline = 0;
        {
            guard held;
            if (!held.acquired) return thread_error_busy;
            u64 now = 0;
            const i64 pumped = pump(now);
            if (pumped) return pumped;
            for (auto& item : children) {
                if (item.terminal_cached && (any || item.pid == child)) {
                    output = item.terminal;
                    delivered(item);
                    return 0;
                }
            }
            bool controlled = false;
            for (const auto& item : children) controlled = controlled || item.channels_open;
            if (!controlled) {
                held.release();
                const i64 result = sdk::syscall(sys_process_wait, child, reinterpret_cast<u64>(&output), flags);
                if (result == 0) {
                    guard completed;
                    if (completed.acquired) if (auto* item = find(output.pid)) delivered(*item);
                }
                return result;
            }
            process_status status{};
            const i64 result = sdk::syscall(sys_process_wait, child, reinterpret_cast<u64>(&status), flags | process_wait_nonblocking);
            if (result == 0) {
                output = status;
                if (auto* item = find(status.pid)) delivered(*item);
                return 0;
            }
            if (result != process_error_would_block || nonblocking) return result;
            wait_set(request, now, deadline);
        }
        pause(request, deadline);
    }
}

i64 notify_ready(const descriptor& control, i64 status, u32 phase) {
    return notify_ready(control, {}, status, phase);
}

i64 notify_ready(const descriptor& control, const artifact& admitted, i64 status, u32 phase) {
    if ((status == 0 && phase) || status > 0 ||
        (status < 0 && (phase < XOS_LAUNCH_PHASE_PREPARE || phase > XOS_LAUNCH_PHASE_COMMIT))) return process_error_invalid;
    if (!artifact_shape(admitted)) return process_error_invalid;
    const message outgoing = make_message(control, admitted, status ? XOS_LAUNCH_FAILURE : XOS_LAUNCH_READY, status, phase);
    message response{};
    const i64 result = exchange(control, outgoing, response);
    if (result) return result;
    if (!status && identity(response, control) && same_artifact(response.artifact, admitted) &&
        response.type == XOS_LAUNCH_READY_ACK && response.status < 0 && response.phase == XOS_LAUNCH_PHASE_ENTRY)
        return response.status;
    return identity(response, control) && same_artifact(response.artifact, admitted) && !response.status && response.phase == phase &&
           response.type == (status ? XOS_LAUNCH_FAILURE_ACK : XOS_LAUNCH_READY_ACK) ? 0 : process_error_invalid;
}

i64 prepare_exec(const descriptor& active, u64 absolute_deadline, descriptor& pending) {
    return prepare_exec(active, absolute_deadline, {}, pending);
}

i64 prepare_exec(const descriptor& active, u64 absolute_deadline, const artifact& requested, descriptor& pending) {
    if (!artifact_shape(requested)) return process_error_invalid;
    const message outgoing = make_message(active, requested, XOS_LAUNCH_PREPARE, 0, 0, absolute_deadline);
    message response{};
    const i64 result = exchange(active, outgoing, response);
    if (result) return result;
    if (response.type != XOS_LAUNCH_ALLOW || response.pid != active.child_pid || response.deadline != absolute_deadline ||
        !same_artifact(response.artifact, requested)) return process_error_invalid;
    if (response.status < 0 && response.phase == XOS_LAUNCH_PHASE_PREPARE && identity(response, active, false)) return response.status;
    if (response.status || response.phase || response.generation <= active.generation || response.nonce == active.nonce)
        return process_error_invalid;
    descriptor next = active;
    next.generation = response.generation;
    next.nonce = response.nonce;
    next.deadline = response.deadline;
    pending = next;
    return 0;
}

i64 cancel_exec(const descriptor& pending) { return cancel_exec(pending, {}); }

i64 cancel_exec(const descriptor& pending, const artifact& admitted) {
    if (!artifact_shape(admitted)) return process_error_invalid;
    const message outgoing = make_message(pending, admitted, XOS_LAUNCH_CANCEL);
    message response{};
    const i64 result = exchange(pending, outgoing, response);
    if (result) return result;
    return identity(response, pending) && same_artifact(response.artifact, admitted) &&
           response.type == XOS_LAUNCH_CANCEL_ACK && !response.status && !response.phase ? 0 : process_error_invalid;
}
}

extern "C" xos::i64 xos_launch_wait_hook(xos::u64 child, xos::process_status* status, xos::u32 flags) {
    if (status == nullptr) return xos::process_error_invalid;
    return xos::launch::wait(child, *status, flags);
}
