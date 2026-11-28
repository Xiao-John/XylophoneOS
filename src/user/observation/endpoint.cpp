// SPDX-License-Identifier: Apache-2.0
#include <xos/observation.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

namespace xos::observation {
namespace {
bool clock(u64& result) {
    const i64 value = sdk::syscall(sys_clock_monotonic);
    if (value < 0) return false;
    result = static_cast<u64>(value); return true;
}
void retire(ipc_channel& channel) {
    if (channel.send) (void)sdk::ipc_channel_close(channel.send);
    if (channel.receive) (void)sdk::ipc_channel_close(channel.receive);
    channel = {};
}
bool peer(const ipc_channel& channel, u64& value) {
    u64 other = 0;
    return channel.send && channel.receive && channel.send != channel.receive &&
        !sdk::ipc_endpoint_peer(channel.send, value) &&
        !sdk::ipc_endpoint_peer(channel.receive, other) && value && value == other;
}
bool zero(const void* data_pointer, u32 length) {
    const auto* bytes = static_cast<const u8*>(data_pointer);
    for (u32 i = 0; i < length; ++i) if (bytes[i]) return false;
    return true;
}
scope default_scope(kind subject) {
    switch (subject) {
    case kind::process: case kind::resource: return scope::self;
    case kind::service: return scope::held_endpoint;
    case kind::runtime: return scope::controller;
    case kind::network: return scope::service;
    case kind::trust: return scope::application;
    }
    return scope::self;
}
}
bool valid_response(const response& value) {
    if (value.version != version || value.size != sizeof(value) || value.reserved ||
        !mask(value.subject) || value.outcome > status::unsupported || !value.sequence ||
        !value.observation_id || !value.server_pid || !value.server_epoch || !value.caller_pid ||
        value.valid_until_ns <= value.observed_at_ns) return false;
    const bool process_scope = value.subject == kind::process || value.subject == kind::resource;
    if ((process_scope && value.origin != scope::self && value.origin != scope::direct_child) ||
        (!process_scope && value.origin != default_scope(value.subject))) return false;
    if (value.outcome != status::ok)
        return !value.object_id && !value.generation && zero(&value.value, sizeof(value.value));
    if (!value.object_id || !value.generation) return false;
    if (process_scope && value.origin == scope::self && value.object_id != value.server_pid) return false;
    u32 words = 0;
    switch (value.subject) {
    case kind::process:
        words = 3;
        if (value.value.values[1] < 1 || value.value.values[1] > 6 || value.value.values[2] > 64) return false;
        if (value.origin == scope::direct_child &&
            (value.value.values[0] != value.server_pid || value.object_id == value.server_pid)) return false;
        break;
    case kind::service:
        words = 3;
        if (!value.value.values[0] || value.value.values[1] != version || value.value.values[2] != 1) return false;
        break;
    case kind::resource:
        words = 6;
        if (value.value.values[0] != value.object_id || value.value.values[1] > value.value.values[2] ||
            value.value.values[2] != ipc_max_owned_channels || value.value.values[3] > value.value.values[4] ||
            value.value.values[4] != ipc_max_owned_names) return false;
        if (value.origin == scope::direct_child &&
            (value.value.values[5] != value.server_pid || value.object_id == value.server_pid)) return false;
        break;
    case kind::runtime: case kind::trust:
        words = 1;
        if (value.value.values[0] != value.server_pid || zero(value.value.digest, 32)) return false;
        if (value.subject == kind::trust && value.object_id != value.generation) return false;
        break;
    case kind::network:
        words = 3;
        if (value.value.values[0] != value.object_id || value.value.values[1] > 2 || value.value.values[2] > 1 ||
            (!value.value.values[1] && value.value.values[2])) return false;
        break;
    }
    if (!zero(value.value.values + words, (10 - words) * sizeof(u64))) return false;
    return value.subject == kind::runtime || value.subject == kind::trust || zero(value.value.digest, 32);
}
status server::initialize(capture_fn capture, void* context) {
    if (epoch_ || !capture) return status::invalid;
    u64 instance = 0;
    if (sdk::syscall(sys_random_bytes, reinterpret_cast<u64>(&instance), sizeof(instance)) || !instance)
        return status::unavailable;
    pid_ = sdk::pid(); epoch_ = instance; capture_ = capture; context_ = context;
    next_observation_ = next_grant_ = 1; return status::ok;
}
status server::authorize(u64 pid, u32 kinds, u32 reads, u64 expires) {
    u64 now = 0;
    if (!epoch_ || !next_grant_ || !pid || !kinds || (kinds & ~all_kinds) || !reads || reads > max_reads || !clock(now) ||
        expires <= now || expires - now > max_grant_ns) return status::invalid;
    u64 generation = 0;
    for (auto& entry : clients_) if (entry.channel.send && entry.peer == pid) {
        observe_native::request query{observe_native::version, sizeof(observe_native::request),
            observe_native::query::service, 0, entry.channel.send, pid, entry.image_generation, expires};
        observe_native::snapshot value{};
        if (sdk::observe(query, value) != observe_native::result::ok) return status::unauthorized;
        generation = value.image_generation; break;
    }
    if (!generation) return status::unauthorized;
    grant* slot = nullptr;
    for (auto& entry : grants_) {
        if (entry.pid == pid) { slot = &entry; break; }
        if (!entry.pid && !slot) slot = &entry;
    }
    if (!slot) return status::quota;
    *slot = {pid, generation, expires, next_grant_++, kinds, reads, false}; return status::ok;
}
status server::revoke(u64 pid) {
    if (!epoch_ || !pid) return status::invalid;
    for (auto& entry : grants_) if (entry.pid == pid) { entry.revoked = true; return status::ok; }
    return status::unauthorized;
}
status server::forget(u64 pid) {
    if (!epoch_ || !pid) return status::invalid;
    bool found = false;
    for (auto& entry : clients_) if (entry.peer == pid) { retire(entry.channel); entry = {}; found = true; }
    for (auto& entry : grants_) if (entry.pid == pid) { entry = {}; found = true; }
    return found ? status::ok : status::unauthorized;
}
status server::attach(ipc_channel channel) {
    u64 identity = 0;
    if (!epoch_ || !peer(channel, identity)) return status::unauthorized;
    u64 now = 0;
    if (!clock(now) || now > ~u64{0} - max_request_ns) return status::unavailable;
    observe_native::request query{observe_native::version, sizeof(observe_native::request),
        observe_native::query::service, 0, channel.send, identity, 0, now + max_request_ns};
    observe_native::snapshot value{};
    if (sdk::observe(query, value) != observe_native::result::ok) return status::unauthorized;
    for (auto& entry : clients_) if (entry.channel.send == channel.send || entry.channel.receive == channel.receive)
        return status::invalid;
    for (auto& entry : clients_) if (!entry.channel.send) {
        entry = {}; entry.channel = channel; entry.peer = identity; entry.image_generation = value.image_generation;
        entry.next_sequence = 1;
        return status::ok;
    }
    return status::quota;
}
void server::handle(connection& entry, const request& input) {
    auto& reply = entry.reply;
    reply = {}; reply.version = version; reply.size = sizeof(reply); reply.outcome = status::invalid;
    reply.subject = input.subject; reply.origin = default_scope(input.subject);
    reply.sequence = input.sequence; reply.server_pid = pid_; reply.server_epoch = epoch_; reply.caller_pid = entry.peer;
    u64 now = 0;
    if (!clock(now) || !next_observation_) { retire(entry.channel); return; }
    reply.observation_id = next_observation_++; reply.observed_at_ns = now; reply.valid_until_ns = input.deadline_ns;
    if (input.version != version || input.size != sizeof(input) || input.operation != 1 || input.reserved ||
        !mask(input.subject) || !input.sequence || input.sequence != entry.next_sequence || !input.deadline_ns ||
        input.deadline_ns == ~u64{0} || (input.deadline_ns > now && input.deadline_ns - now > max_request_ns)) {
        // Invalid input must never extend a pending mailbox lease to infinity.
        if (now > ~u64{0} - max_request_ns) { retire(entry.channel); return; }
        if (reply.valid_until_ns <= now || reply.valid_until_ns - now > max_request_ns)
            reply.valid_until_ns = now + max_request_ns;
        entry.pending = true; return;
    }
    ++entry.next_sequence;
    if (input.deadline_ns <= now) reply.outcome = status::deadline;
    else if (input.server_epoch != epoch_) reply.outcome = status::stale;
    else {
        grant* authority = nullptr;
        for (auto& item : grants_) if (item.pid == entry.peer) { authority = &item; break; }
        if (!authority || authority->image_generation != entry.image_generation ||
            !(authority->kinds & mask(input.subject))) reply.outcome = status::unauthorized;
        else if (authority->revoked) reply.outcome = status::revoked;
        else if (authority->expires <= now) reply.outcome = status::stale;
        else if (!authority->remaining) reply.outcome = status::quota;
        else {
            --authority->remaining;
            entry.grant_revision = authority->revision;
            if (authority->expires < reply.valid_until_ns) reply.valid_until_ns = authority->expires;
            response captured{};
            reply.outcome = capture_(context_, input.subject, reply.valid_until_ns, captured);
            reply.origin = captured.origin; reply.object_id = captured.object_id;
            reply.generation = captured.generation; reply.value = captured.value;
            u64 completed = 0;
            if (!clock(completed)) reply.outcome = status::unavailable;
            else if (completed >= reply.valid_until_ns) reply.outcome = status::deadline;
            else if (reply.outcome == status::ok &&
                    ((input.expected_object && input.expected_object != reply.object_id) ||
                     (input.expected_generation && input.expected_generation != reply.generation))) reply.outcome = status::stale;
        }
    }
    if (reply.outcome != status::ok) {
        reply.object_id = reply.generation = 0; reply.value = {};
        reply.origin = default_scope(input.subject);
    }
    if (reply.outcome == status::ok && !valid_response(reply)) {
        reply.outcome = status::unavailable; reply.object_id = reply.generation = 0; reply.value = {};
        reply.origin = default_scope(input.subject);
    }
    entry.pending = true;
}
u32 server::poll() {
    u32 handled = 0;
    for (auto& entry : clients_) {
        if (!entry.channel.send) continue;
        u64 identity = 0;
        if (!peer(entry.channel, identity) || identity != entry.peer) { retire(entry.channel); continue; }
        u64 checked_at = 0;
        if (!clock(checked_at) || checked_at > ~u64{0} - max_request_ns) { retire(entry.channel); continue; }
        // Attachment never authorizes a replacement process image. The actual
        // transport is sys84/86; native source observation also supports sys81.
        observe_native::request identity_query{observe_native::version, sizeof(observe_native::request),
            observe_native::query::service, 0, entry.channel.send, entry.peer,
            entry.image_generation, checked_at + max_request_ns};
        observe_native::snapshot identity_value{};
        if (sdk::observe(identity_query, identity_value) != observe_native::result::ok) {
            retire(entry.channel); entry.pending = false; continue;
        }
        if (!entry.pending) {
            request input{};
            const i64 received = sdk::ipc_recv(entry.channel.receive, &input, sizeof(input));
            if (received == -3) continue;
            if (received != sizeof(input)) { retire(entry.channel); continue; }
            handle(entry, input); ++handled;
        }
        if (!entry.channel.send || !entry.pending) continue;
        u64 now = 0;
        if (!clock(now) || now >= entry.reply.valid_until_ns) {
            retire(entry.channel); entry.pending = false; continue;
        }
        // Revalidate a captured success before it enters the mailbox. A reply
        // already queued before revocation is a historical authorized read.
        if (entry.reply.outcome == status::ok) {
            // Capture can wait for another service. Recheck the live peer after
            // it returns, rather than relying on the identity at poll entry.
            identity_query.deadline_ns = entry.reply.valid_until_ns;
            if (sdk::observe(identity_query, identity_value) != observe_native::result::ok) {
                retire(entry.channel); entry.pending = false; entry.reply = {}; continue;
            }
            grant* authority = nullptr;
            for (auto& item : grants_) if (item.pid == entry.peer) { authority = &item; break; }
            status gate = status::ok;
            if (!authority || authority->image_generation != entry.image_generation ||
                !(authority->kinds & mask(entry.reply.subject))) gate = status::unauthorized;
            else if (authority->revoked) gate = status::revoked;
            else if (authority->revision != entry.grant_revision || authority->expires <= now) gate = status::stale;
            if (gate != status::ok) {
                entry.reply.outcome = gate; entry.reply.object_id = entry.reply.generation = 0;
                entry.reply.value = {}; entry.reply.origin = default_scope(entry.reply.subject);
            }
        }
        const i64 sent = sdk::ipc_send(entry.channel.send, &entry.reply, sizeof(entry.reply));
        if (!sent) entry.pending = false;
        else if (sent != ipc_error_full) { retire(entry.channel); entry.pending = false; }
    }
    return handled;
}
void server::close() {
    for (auto& entry : clients_) { retire(entry.channel); entry = {}; }
    for (auto& entry : grants_) entry = {};
    pid_ = epoch_ = 0; capture_ = nullptr; context_ = nullptr;
}
status client::connect(const char* name, u64 pid, u64 epoch) {
    if (channel_.send || !name || !pid || !epoch) return status::invalid;
    const i64 result = sdk::ipc_name_connect(name, channel_);
    if (result) { close(); return result == process_error_resources ? status::quota : status::unavailable; }
    u64 actual = 0;
    if (!peer(channel_, actual) || actual != pid) { close(); return status::stale; }
    pid_ = pid; epoch_ = epoch; sequence_ = 1; return status::ok;
}
status client::read(kind subject, u64 deadline, response& output, u64 object, u64 generation) {
    output = {};
    u64 now = 0;
    if (!channel_.send || !mask(subject) || !sequence_ || !deadline || deadline == ~u64{0}) return status::invalid;
    if (!clock(now)) { close(); return status::unavailable; }
    if (deadline <= now) return status::deadline;
    if (deadline - now > max_request_ns) return status::invalid;
    const request input{version, sizeof(request), 1, subject, sequence_++, deadline, epoch_, object, generation, 0};
    for (;;) {
        if (!clock(now)) { close(); return status::unavailable; }
        if (now >= deadline) { close(); return status::deadline; }
        const i64 sent = sdk::ipc_send(channel_.send, &input, sizeof(input));
        if (!sent) break;
        if (sent != ipc_error_full) { close(); return status::revoked; }
        const i64 waited = sdk::ipc_wait_until(channel_.send, ipc_wait_mode::send, deadline);
        if (!clock(now) || now >= deadline || waited == thread_error_timeout) { close(); return status::deadline; }
        if (waited) { close(); return status::revoked; }
    }
    for (;;) {
        response reply{};
        const i64 received = sdk::ipc_recv(channel_.receive, &reply, sizeof(reply));
        if (!clock(now)) { close(); return status::unavailable; }
        if (now >= deadline) { close(); return status::deadline; }
        if (received == -3) {
            const i64 waited = sdk::ipc_wait_until(channel_.receive, ipc_wait_mode::receive, deadline);
            if (waited == thread_error_timeout) { close(); return status::deadline; }
            if (waited) { close(); return status::revoked; }
            continue;
        }
        if (received < 0) { close(); return status::revoked; }
        if (received != sizeof(reply) || !valid_response(reply) || reply.sequence != input.sequence ||
            reply.subject != subject || reply.server_pid != pid_ ||
            reply.caller_pid != sdk::pid() || reply.valid_until_ns > deadline ||
            reply.observed_at_ns > now) { close(); return status::invalid; }
        if (now >= reply.valid_until_ns) { close(); return status::deadline; }
        if (reply.server_epoch != epoch_) {
            if (reply.outcome == status::stale) { output = reply; close(); return status::stale; }
            close(); return status::invalid;
        }
        if (reply.outcome == status::ok &&
            ((object && reply.object_id != object) || (generation && reply.generation != generation))) {
            close(); return status::stale;
        }
        output = reply; return reply.outcome;
    }
}
void client::close() { retire(channel_); pid_ = epoch_ = 0; sequence_ = 1; }
}
