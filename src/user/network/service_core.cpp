// SPDX-License-Identifier: Apache-2.0
#include "service_core.hpp"

namespace xos::user::network {
using namespace net2;
namespace {
bool normalize_name(const u8* input, u32 length, char (&name)[dns_name_limit + 1]) {
    if (!length || length > dns_name_limit + 1) return false;
    if (input[length - 1] == '.') --length;
    if (!length || length > dns_name_limit) return false;
    u32 label_length = 0;
    bool has_letter = false;
    for (u32 i = 0; i < length; ++i) {
        u8 character = input[i];
        if (character >= 'A' && character <= 'Z') character += 'a' - 'A';
        const bool letter = character >= 'a' && character <= 'z';
        const bool digit = character >= '0' && character <= '9';
        if (character == '.') {
            if (!label_length || name[i - 1] == '-') return false;
            label_length = 0;
        } else {
            if ((!letter && !digit && (character != '-' || !label_length)) || ++label_length > 63) return false;
            has_letter |= letter;
        }
        name[i] = static_cast<char>(character);
    }
    return label_length && name[length - 1] != '-' && has_letter;
}
}

void service_core::initialize(u64 controller, const stack_api& stack, const resolver_api& resolver,
                              u32 configured_resolver, const egress_policy& policy) {
    policy_ = valid_egress_policy(policy) ? policy : egress_policy{};
    controller_ = controller; stack_ = stack; resolver_ = resolver;
    if (valid_static_resolver(configured_resolver) && resolver_.configure) {
        resolver_address_ = configured_resolver;
        resolver_.configure(resolver_.context, resolver_address_);
        mode_ = network_mode::static_direct;
    }
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
    if (slot < client_sessions) retire_ticket(slot);
    for (u32 i = 0; i < connection_limit; ++i)
        if (connections_[i].handle && connections_[i].owner == slot) release(i);
    sessions_[slot] = {};
}
void service_core::expire(u64 now) {
    for (u32 i = 0; i < session_limit; ++i)
        if (alive(i) && now >= sessions_[i].last_active && now - sessions_[i].last_active >= idle_ns) detach(i);
    for (auto& item : tickets_) {
        if (!item.id || item.result != would_block || now < item.deadline) continue;
        resolver_.cancel(resolver_.context, item.id);
        item.result = timeout;
    }
}
void service_core::shutdown() { for (u32 i = 0; i < session_limit; ++i) detach(i); }
i64 service_core::find_connection(u32 owner, u64 handle) const {
    if (!handle) return invalid;
    for (u32 i = 0; i < connection_limit; ++i)
        if (connections_[i].handle == handle)
            return connections_[i].owner == owner ? static_cast<i64>(i) : denied;
    return closed;
}

void service_core::retire_ticket(u32 slot) {
    auto& item = tickets_[slot];
    if (item.id && item.result == would_block) resolver_.cancel(resolver_.context, item.id);
    item = {};
}

void service_core::complete_ticket(void* context, u64 id, i64 result, u32 address, u64 expiry, u64 received) {
    auto& self = *static_cast<service_core*>(context);
    for (u32 owner = 0; owner < client_sessions; ++owner) {
        auto& item = self.tickets_[owner];
        if (item.id != id || item.generation != self.generation(owner) || item.epoch != self.config_epoch_ ||
            item.result != would_block) continue;
        item.result = received >= item.deadline ? timeout : result;
        item.address = address;
        item.expiry = expiry;
        return;
    }
}

bool service_core::resolve(u32 slot, const message& input, u64 now, message& output) {
    if (!resolver_.start) { output.result = unsupported; return true; }
    if (input.action == operation::configuration || input.action == operation::configure) {
        if (input.object) { output.result = invalid; return true; }
        u32 count = 0;
        for (const auto& item : tickets_) if (item.id) ++count;
        if (input.action == operation::configure) {
            if (sessions_[slot].peer != controller_) { output.result = denied; return true; }
            if (input.length != sizeof(config_request)) { output.result = invalid; return true; }
            config_request requested{};
            __builtin_memcpy(&requested, input.data, sizeof(requested));
            if (requested.revision != configuration_revision ||
                (requested.mode != network_mode::disabled && requested.mode != network_mode::static_direct)) {
                output.result = invalid; return true;
            }
            if (requested.expected_epoch != config_epoch_) { output.result = config_changed; return true; }
            if (count || connection_count() || config_epoch_ == ~u64{0}) { output.result = resources; return true; }
            resolver_.configure(resolver_.context,
                                requested.mode == network_mode::static_direct ? resolver_address_ : 0);
            mode_ = requested.mode;
            ++config_epoch_;
        }
        const config_snapshot snapshot{configuration_revision, mode_, config_epoch_, resolve_in_a, static_address,
                                       static_mask, permitted_address,
                                       mode_ == network_mode::static_direct ? resolver_address_ : 0, count, 0};
        __builtin_memcpy(output.data, &snapshot, sizeof(snapshot));
        output.length = sizeof(snapshot);
        return true;
    }
    if (slot >= client_sessions) { output.result = denied; return true; }
    auto& item = tickets_[slot];
    if (input.action == operation::resolve_start) {
        if (mode_ == network_mode::disabled) { output.result = closed; return true; }
        char name[dns_name_limit + 1]{};
        if (input.object || !normalize_name(input.data, input.length, name)) { output.result = invalid; return true; }
        if (item.id || !next_ticket_) { output.result = resources; return true; }
        item = {next_ticket_++, generation(slot), config_epoch_, input.deadline, 0, would_block, 0};
        output.result = resolver_.start(resolver_.context, name, item.id, complete_ticket, this);
        if (output.result) item = {};
        else output.object = item.id;
        return true;
    }
    if (!input.object) { output.result = invalid; return true; }
    if (input.object != item.id) {
        output.result = closed;
        for (const auto& other : tickets_) if (other.id == input.object) { output.result = denied; break; }
        return true;
    }
    if (input.action == operation::resolve_cancel) { retire_ticket(slot); return true; }
    if (now >= item.deadline) output.result = timeout;
    else if (item.result == 0 && item.expiry && now >= item.expiry) output.result = dns_expired;
    else output.result = item.result;
    if (output.result == would_block) return true;
    if (!output.result) {
        const resolve_reply resolved{item.epoch, item.expiry, item.address, 0};
        __builtin_memcpy(output.data, &resolved, sizeof(resolved));
        output.length = sizeof(resolved);
    }
    retire_ticket(slot);
    return true;
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
    const bool assigns_object = input.action == operation::open || input.action == operation::resolve_start;
    output.object = assigns_object ? 0 : input.object;
    if (!input.deadline || input.deadline <= now || input.deadline - now > max_request_ns) {
        output.result = timeout; return true;
    }
    const bool opening = input.action == operation::open;
    if ((!opening && (input.address || input.port || input.transport != protocol::none)) ||
        (input.action != operation::send && input.action != operation::configure &&
         input.action != operation::resolve_start && input.length) ||
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
    if (input.action == operation::capabilities) {
        if (input.object) { output.result = invalid; return true; }
        const capability_snapshot capabilities{socket_extension_revision,
            (stack_.readiness ? capability_readiness : 0) |
            (stack_.shutdown_write ? capability_shutdown_write : 0), 0};
        __builtin_memcpy(output.data, &capabilities, sizeof(capabilities));
        output.length = sizeof(capabilities);
        return true;
    }
    if (input.action >= operation::configuration && input.action <= operation::resolve_cancel)
        return resolve(slot, input, now, output);
    if (opening) {
        if (input.object || !input.port || (input.transport != protocol::tcp && input.transport != protocol::udp)) {
            output.result = invalid; return true;
        }
        if (!egress_permitted(policy_, input.address, input.transport, input.port)) {
            output.result = denied; return true;
        }
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
    if ((static_cast<u32>(input.action) < static_cast<u32>(operation::status) ||
         static_cast<u32>(input.action) > static_cast<u32>(operation::cancel)) &&
        input.action != operation::readiness && input.action != operation::shutdown_write) {
        output.result = unsupported; return true;
    }
    const i64 found = find_connection(slot, input.object);
    if (found < 0) { output.result = found; return true; }
    const u32 connection_slot = static_cast<u32>(found);
    switch (input.action) {
    case operation::status:
        output.result = stack_.status(stack_.context, connection_slot, output.flags); break;
    case operation::readiness: {
        readiness_snapshot snapshot{};
        output.result = stack_.readiness ? stack_.readiness(stack_.context, connection_slot, snapshot) : unsupported;
        if (!output.result) {
            __builtin_memcpy(output.data, &snapshot, sizeof(snapshot));
            output.length = sizeof(snapshot);
        }
        break;
    }
    case operation::shutdown_write:
        output.result = stack_.shutdown_write ? stack_.shutdown_write(stack_.context, connection_slot) : unsupported;
        break;
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
