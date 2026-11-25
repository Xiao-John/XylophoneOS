// SPDX-License-Identifier: Apache-2.0
#include "service_core.hpp"

namespace xos::user::network {
using namespace net2;
void service_core::initialize(u64 controller, const stack_api& stack) {
    controller_ = controller; stack_ = stack;
}
u32 service_core::session_count() const {
    u32 count = 0; for (const auto& item : sessions_) if (item.peer) ++count; return count;
}
u32 service_core::connection_count() const {
    u32 count = 0; for (const auto& item : connections_) if (item.handle) ++count; return count;
}
bool service_core::alive(u32 slot) const { return slot < session_limit && sessions_[slot].peer; }
u64 service_core::peer(u32 slot) const { return alive(slot) ? sessions_[slot].peer : 0; }
u64 service_core::generation(u32 slot) const { return alive(slot) ? sessions_[slot].generation : 0; }
i64 service_core::attach(u64 peer_pid, u64 now) {
    if (!peer_pid || stopping_) return closed;
    if (!next_generation_) return resources;
    for (const auto revoked : revoked_) if (revoked == peer_pid) return denied;
    for (const auto& item : sessions_) if (item.peer == peer_pid) return resources;
    const u32 first = peer_pid == controller_ ? client_sessions : 0;
    const u32 end = peer_pid == controller_ ? session_limit : client_sessions;
    for (u32 i = first; i < end; ++i) if (!sessions_[i].peer) {
        sessions_[i] = {peer_pid, 0, now, next_generation_++}; return i;
    }
    return resources;
}
void service_core::release(u32 slot) {
    if (connections_[slot].handle) (void)stack_.close(stack_.context, slot, true);
    connections_[slot] = {};
}
void service_core::detach(u32 slot) {
    if (!alive(slot)) return;
    for (u32 i = 0; i < connection_limit; ++i)
        if (connections_[i].handle && connections_[i].owner == slot) release(i);
    sessions_[slot] = {};
}
void service_core::expire(u64 now) {
    for (u32 i = 0; i < session_limit; ++i)
        if (alive(i) && now >= sessions_[i].last_active && now - sessions_[i].last_active >= idle_ns) detach(i);
}
void service_core::shutdown() { for (u32 i = 0; i < session_limit; ++i) detach(i); }
i64 service_core::find_connection(u32 owner, u64 handle) const {
    if (!handle) return invalid;
    for (u32 i = 0; i < connection_limit; ++i)
        if (connections_[i].handle == handle)
            return connections_[i].owner == owner ? static_cast<i64>(i) : denied;
    return closed;
}
bool service_core::dispatch(u32 slot, const message& input, u32 bytes, u64 now, message& output) {
    output = {};
    if (!alive(slot) || bytes < header_bytes || input.version != version ||
        input.reserved || input.result || input.length > payload_bytes ||
        bytes != header_bytes + input.length || !input.sequence ||
        sessions_[slot].last_sequence == ~u64{0} || input.sequence != sessions_[slot].last_sequence + 1) return false;
    sessions_[slot].last_sequence = input.sequence;
    sessions_[slot].last_active = now;
    output.version = version; output.action = input.action; output.sequence = input.sequence;
    output.object = input.action == operation::open ? 0 : input.object;
    if (!input.deadline || input.deadline <= now || input.deadline - now > max_request_ns) {
        output.result = timeout; return true;
    }
    const bool opening = input.action == operation::open;
    if ((!opening && (input.address || input.port || input.transport != protocol::none)) ||
        (input.action != operation::send && input.length) ||
        (input.action != operation::receive && input.flags)) {
        output.result = invalid; return true;
    }
    if (input.action == operation::information) {
        if (input.object) { output.result = invalid; return true; }
        const information info{session_count(), connection_count(), client_sessions, connection_limit,
                               payload_bytes, connections_per_session, stack_.dropped(stack_.context), 0};
        const auto* source = reinterpret_cast<const u8*>(&info);
        for (u32 i = 0; i < sizeof(info); ++i) output.data[i] = source[i];
        output.length = sizeof(info); return true;
    }
    if (input.action == operation::stop || input.action == operation::revoke_peer) {
        if (sessions_[slot].peer != controller_) { output.result = denied; return true; }
        if (input.action == operation::stop) {
            if (input.object) output.result = invalid; else stopping_ = true;
            return true;
        }
        if (!input.object || input.object == controller_) { output.result = invalid; return true; }
        u32 free = 16;
        for (u32 i = 0; i < 16; ++i) {
            if (revoked_[i] == input.object) { free = i; break; }
            if (!revoked_[i]) free = i;
        }
        if (free == 16) { output.result = resources; return true; }
        revoked_[free] = input.object;
        for (u32 i = 0; i < session_limit; ++i) if (sessions_[i].peer == input.object) detach(i);
        return true;
    }
    if (stopping_) { output.result = closed; return true; }
    if (opening) {
        if (input.object || !input.port || (input.transport != protocol::tcp && input.transport != protocol::udp)) {
            output.result = invalid; return true;
        }
        if (input.address != permitted_address) { output.result = denied; return true; }
        u32 owned = 0, free = connection_limit;
        for (u32 i = 0; i < connection_limit; ++i) {
            if (!connections_[i].handle) free = i;
            else if (connections_[i].owner == slot) ++owned;
        }
        if (!next_handle_ || owned >= connections_per_session || free == connection_limit) {
            output.result = resources; return true;
        }
        output.result = stack_.open(stack_.context, free, input.transport, input.address, input.port, input.deadline);
        if (output.result) return true;
        connections_[free] = {next_handle_++, slot}; output.object = connections_[free].handle;
        output.result = stack_.status(stack_.context, free, output.flags);
        if (output.result) { release(free); output.object = 0; }
        return true;
    }
    if (static_cast<u32>(input.action) < static_cast<u32>(operation::status) ||
        static_cast<u32>(input.action) > static_cast<u32>(operation::cancel)) {
        output.result = unsupported; return true;
    }
    const i64 found = find_connection(slot, input.object);
    if (found < 0) { output.result = found; return true; }
    const u32 connection_slot = static_cast<u32>(found);
    switch (input.action) {
    case operation::status:
        output.result = stack_.status(stack_.context, connection_slot, output.flags); break;
    case operation::send:
        output.result = stack_.send(stack_.context, connection_slot, input.data, input.length); break;
    case operation::receive:
        if (!input.flags || input.flags > payload_bytes) { output.result = invalid; break; }
        output.result = stack_.receive(stack_.context, connection_slot, output.data, input.flags,
                                      output.length, output.flags); break;
    case operation::close:
    case operation::cancel:
        output.result = stack_.close(stack_.context, connection_slot, input.action == operation::cancel);
        if (!output.result) connections_[connection_slot] = {};
        break;
    default: output.result = unsupported; break;
    }
    return true;
}
}
