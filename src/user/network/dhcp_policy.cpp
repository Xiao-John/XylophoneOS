// SPDX-License-Identifier: Apache-2.0
#include "dhcp_policy.hpp"

namespace xos::user::network::dhcp {
namespace {
u32 read_u32(const u8* value) {
    return (static_cast<u32>(value[0]) << 24) | (static_cast<u32>(value[1]) << 16) |
           (static_cast<u32>(value[2]) << 8) | value[3];
}
bool unicast(u32 address) {
    const u32 first = address >> 24;
    return first != 0 && first != 127 && first < 224;
}
bool subnet_host(u32 address, const policy& authority) {
    const u32 host = address & ~authority.mask;
    return unicast(address) && (address & authority.mask) == authority.subnet &&
           host != 0 && host != ~authority.mask;
}
bool contains(const u32* list, u32 count, u32 address) {
    for (u32 i = 0; i < count; ++i) if (list[i] == address) return true;
    return false;
}
bool valid_list(const u32* list, u32 count) {
    if (count > authority_limit) return false;
    for (u32 i = 0; i < authority_limit; ++i) {
        if (i >= count) { if (list[i]) return false; }
        else if (!unicast(list[i]) || contains(list, i, list[i])) return false;
    }
    return true;
}
bool admitted_address(u32 address, const policy& authority) {
    return subnet_host(address, authority) && address >= authority.first_address &&
           address <= authority.last_address &&
           !contains(authority.servers, authority.server_count, address) &&
           !contains(authority.gateways, authority.gateway_count, address) &&
           !contains(authority.resolvers, authority.resolver_count, address);
}
error relative_times(const reply& value, u64& duration, u64& t1, u64& t2) {
    if (!value.lease_seconds || value.lease_seconds == ~u32{0}) return error::timing;
    // Every finite u32 second count fits a u64 nanosecond duration. Widen before
    // multiplication; use a split ratio so 7 * duration cannot overflow.
    duration = static_cast<u64>(value.lease_seconds) * second_ns;
    t1 = value.has_t1 ? static_cast<u64>(value.t1_seconds) * second_ns : duration / 2;
    t2 = value.has_t2 ? static_cast<u64>(value.t2_seconds) * second_ns :
         (duration / 8) * 7 + ((duration % 8) * 7) / 8;
    if (!t1 || t1 >= t2 || t2 >= duration) return error::timing;
    return error::none;
}
bool same_configuration(const reply& left, const reply& right) {
    if (left.address != right.address || left.mask != right.mask || left.gateway != right.gateway ||
        left.resolver_count != right.resolver_count) return false;
    for (u32 i = 0; i < left.resolver_count; ++i)
        if (left.resolvers[i] != right.resolvers[i]) return false;
    return true;
}
bool request_state(state value) {
    return value == state::requesting || value == state::renewing || value == state::rebinding;
}
}

error validate_policy(const policy& authority) {
    const u32 inverse = ~authority.mask;
    if (!authority.mask || inverse < 3 || (inverse & (inverse + 1)) ||
        (authority.subnet & authority.mask) != authority.subnet ||
        authority.first_address > authority.last_address ||
        !subnet_host(authority.first_address, authority) ||
        !subnet_host(authority.last_address, authority) ||
        !authority.server_count || !valid_list(authority.servers, authority.server_count) ||
        !valid_list(authority.gateways, authority.gateway_count) ||
        !valid_list(authority.resolvers, authority.resolver_count) ||
        !authority.max_lease_seconds || authority.max_lease_seconds == ~u32{0}) return error::authority;
    for (u32 i = 0; i < authority.server_count; ++i)
        if (!subnet_host(authority.servers[i], authority)) return error::authority;
    for (u32 i = 0; i < authority.gateway_count; ++i)
        if (!subnet_host(authority.gateways[i], authority)) return error::authority;
    const u32* lists[] = {authority.servers, authority.gateways, authority.resolvers};
    const u32 counts[] = {authority.server_count, authority.gateway_count, authority.resolver_count};
    for (u32 list = 0; list < 3; ++list)
        for (u32 i = 0; i < counts[list]; ++i)
            if (lists[list][i] >= authority.first_address && lists[list][i] <= authority.last_address)
                return error::authority;
    return error::none;
}

error validate_reply(const u8* bytes, u32 length, u32 source_address,
                     u16 source_port, const reply_context& expected,
                     const policy& authority, reply& output) {
    if (!bytes || length < 241 || length > reply_limit) return error::argument;
    if (validate_policy(authority) != error::none) return error::authority;
    if (source_port != 67 || !contains(authority.servers, authority.server_count, source_address))
        return error::identity;
    if (expected.state == phase::selecting) {
        if (expected.selected_server || expected.requested_address) return error::state;
    } else if (expected.state == phase::requesting || expected.state == phase::renewing ||
               expected.state == phase::rebinding) {
        if (!admitted_address(expected.requested_address, authority) ||
            !contains(authority.servers, authority.server_count, expected.selected_server)) return error::state;
    } else return error::state;
    u8 mac_bits = 0;
    for (u32 i = 0; i < 6; ++i) mac_bits |= expected.mac[i];
    if (!mac_bits || (expected.mac[0] & 1)) return error::argument;
    if (bytes[0] != 2 || bytes[1] != 1 || bytes[2] != 6 || bytes[3] ||
        (bytes[10] & 0x7f) || bytes[11] || read_u32(bytes + 24) ||
        read_u32(bytes + 236) != 0x63825363) return error::header;
    if (read_u32(bytes + 4) != expected.xid) return error::identity;
    for (u32 i = 0; i < 16; ++i)
        if (bytes[28 + i] != (i < 6 ? expected.mac[i] : 0)) return error::identity;
    const u32 ciaddr = read_u32(bytes + 12);
    if (ciaddr && (expected.state == phase::selecting || expected.state == phase::requesting ||
                   ciaddr != expected.requested_address)) return error::identity;

    reply parsed{};
    parsed.xid = expected.xid;
    parsed.address = read_u32(bytes + 16);
    bool seen[256]{}, ended = false;
    for (u32 offset = 240; offset < length;) {
        const u8 code = bytes[offset++];
        if (!code) continue;
        if (code == 255) {
            for (; offset < length; ++offset) if (bytes[offset]) return error::options;
            ended = true;
            break;
        }
        if (seen[code] || offset == length) return error::options;
        seen[code] = true;
        const u32 size = bytes[offset++];
        if (size > length - offset) return error::options;
        const u8* value = bytes + offset;
        switch (code) {
        case 1:
            if (size != 4 || seen[3]) return error::options;
            parsed.mask = read_u32(value);
            break;
        case 3:
            if (size != 4) return error::options;
            parsed.gateway = read_u32(value);
            break;
        case 6:
            if (!size || size % 4 || size / 4 > authority_limit) return error::options;
            parsed.resolver_count = size / 4;
            for (u32 i = 0; i < parsed.resolver_count; ++i) {
                parsed.resolvers[i] = read_u32(value + i * 4);
                if (contains(parsed.resolvers, i, parsed.resolvers[i])) return error::options;
            }
            break;
        case 51: case 54: case 58: case 59:
            if (size != 4) return error::options;
            if (code == 51) parsed.lease_seconds = read_u32(value);
            if (code == 54) parsed.server = read_u32(value);
            if (code == 58) { parsed.t1_seconds = read_u32(value); parsed.has_t1 = true; }
            if (code == 59) { parsed.t2_seconds = read_u32(value); parsed.has_t2 = true; }
            break;
        case 53:
            if (size != 1) return error::options;
            parsed.type = static_cast<message_type>(value[0]);
            break;
        case 61:
            if (size != 7 || value[0] != 1) return error::identity;
            for (u32 i = 0; i < 6; ++i) if (value[i + 1] != expected.mac[i]) return error::identity;
            break;
        case 33: case 52: case 121: case 249:
            return error::options;
        default:
            break; // Unknown data cannot become routing, identity or DNS policy.
        }
        offset += size;
    }
    if (!ended || !seen[53] || !seen[54]) return error::options;
    if (parsed.server != source_address ||
        (expected.state != phase::selecting && expected.state != phase::rebinding &&
         parsed.server != expected.selected_server)) return error::identity;
    if (expected.state == phase::selecting) {
        if (parsed.type != message_type::offer) return error::state;
    } else if (parsed.type != message_type::ack && parsed.type != message_type::nak) return error::state;
    if (parsed.type == message_type::nak) {
        if (ciaddr || parsed.address || seen[1] || seen[3] || seen[6] || seen[51] || seen[58] || seen[59])
            return error::options;
        output = parsed;
        return error::none;
    }
    if (!seen[1] || !seen[51] || parsed.mask != authority.mask ||
        !admitted_address(parsed.address, authority) ||
        (expected.state != phase::selecting && parsed.address != expected.requested_address) ||
        (authority.gateway_count ? (!seen[3] || !contains(authority.gateways, authority.gateway_count, parsed.gateway)) : seen[3]) ||
        (authority.resolver_count ? !seen[6] : seen[6])) return error::authority;
    for (u32 i = 0; i < parsed.resolver_count; ++i)
        if (!contains(authority.resolvers, authority.resolver_count, parsed.resolvers[i])) return error::authority;
    if (parsed.lease_seconds > authority.max_lease_seconds) return error::authority;
    u64 duration = 0, t1 = 0, t2 = 0;
    const error timing = relative_times(parsed, duration, t1, t2);
    if (timing != error::none) return timing;
    output = parsed;
    return error::none;
}

error lease_clock::start(u64 now, u64 acquisition_deadline) {
    if (published_ || pending_ || (state_ != state::disabled && state_ != state::failed && state_ != state::expired))
        return error::state;
    if (now < last_now_) return error::clock_regressed;
    if (acquisition_deadline == ~u64{0} || acquisition_deadline <= now ||
        acquisition_deadline - now > acquisition_limit_ns) return error::timing;
    current_ = {};
    candidate_ = {};
    request_recorded_ = false;
    request_sent_ = 0;
    request_xid_ = 0;
    acquisition_deadline_ = acquisition_deadline;
    last_now_ = now;
    state_ = state::selecting;
    reason_ = reason::none;
    return error::none;
}

error lease_clock::note_request_sent(phase request_phase, u32 xid, u64 now) {
    if (now < last_now_) return error::clock_regressed;
    if (pending_) return error::state;
    if (published_ && now >= current_.expires) return error::expired;
    if (!published_ && (!acquisition_deadline_ || now >= acquisition_deadline_)) return error::expired;
    state next;
    if (request_phase == phase::requesting && (state_ == state::selecting || state_ == state::requesting))
        next = state::requesting;
    else if (request_phase == phase::renewing && published_ && (state_ == state::bound || state_ == state::renewing))
        next = state::renewing;
    else if (request_phase == phase::rebinding && published_ &&
             (state_ == state::bound || state_ == state::renewing || state_ == state::rebinding))
        next = state::rebinding;
    else return error::state;
    if (!request_recorded_ || xid != request_xid_) {
        if (bound_xid_recorded_ && xid == last_bound_xid_) return error::identity;
        request_recorded_ = true;
        request_xid_ = xid;
        request_sent_ = now;
    }
    last_now_ = now;
    state_ = next;
    return error::none;
}

error lease_clock::accept_ack(const reply& ack, u64 now, candidate_result& output) {
    if (now < last_now_) return error::clock_regressed;
    if (!request_recorded_ || !request_state(state_) || ack.type != message_type::ack || pending_)
        return error::state;
    if (ack.xid != request_xid_) return error::identity;
    if ((published_ && (now >= current_.expires || ack.address != current_.configuration.address)) ||
        (!published_ && now >= acquisition_deadline_)) return error::expired;
    u64 duration = 0, t1 = 0, t2 = 0;
    const error timing = relative_times(ack, duration, t1, t2);
    if (timing != error::none) return timing;
    if (duration > ~u64{0} - request_sent_ || generation_ == ~u64{0}) return error::overflow;
    const lease accepted{ack, request_sent_, request_sent_ + t1, request_sent_ + t2, request_sent_ + duration};
    if (now >= accepted.expires) return error::expired;
    candidate_ = accepted;
    pending_ = true;
    ++generation_;
    state_ = state::checking;
    last_now_ = now;
    output = {generation_, !published_, !published_ || !same_configuration(current_.configuration, ack)};
    return error::none;
}

error lease_clock::approve_address(u64 generation, u64 now, bool& configuration_changed) {
    if (now < last_now_) return error::clock_regressed;
    if (!pending_ || state_ != state::checking || generation != generation_) return error::state;
    if (now >= candidate_.expires || (published_ && now >= current_.expires) ||
        (!published_ && now >= acquisition_deadline_)) return error::expired;
    const bool changed = !published_ || !same_configuration(current_.configuration, candidate_.configuration);
    current_ = candidate_;
    candidate_ = {};
    pending_ = false;
    published_ = true;
    request_recorded_ = false;
    request_xid_ = 0;
    request_sent_ = 0;
    last_bound_xid_ = current_.configuration.xid;
    bound_xid_recorded_ = true;
    acquisition_deadline_ = 0;
    last_now_ = now;
    state_ = state::bound;
    configuration_changed = changed;
    return error::none;
}

error lease_clock::accept_nak(const reply& nak, u64 now, bool& revoke) {
    if (now < last_now_) return error::clock_regressed;
    if (!request_recorded_ || !request_state(state_) || nak.type != message_type::nak || pending_)
        return error::state;
    if (nak.xid != request_xid_) return error::identity;
    if ((published_ && now >= current_.expires) || (!published_ && now >= acquisition_deadline_))
        return error::expired;
    last_now_ = now;
    revoke = invalidate(reason::nak);
    return error::none;
}

bool lease_clock::invalidate(reason cause) {
    const bool revoke = published_;
    published_ = false;
    pending_ = false;
    request_recorded_ = false;
    current_ = {};
    candidate_ = {};
    request_xid_ = 0;
    request_sent_ = 0;
    acquisition_deadline_ = 0;
    reason_ = cause;
    state_ = cause == reason::stopped ? state::disabled :
             (cause == reason::expiry ? state::expired : state::failed);
    return revoke;
}

event lease_clock::advance(u64 now) {
    if (state_ == state::disabled || state_ == state::failed || state_ == state::expired)
        return {action::none, false};
    if (now < last_now_) return {action::clock_failed, invalidate(reason::clock_failure)};
    last_now_ = now;
    if ((published_ && now >= current_.expires) || (pending_ && now >= candidate_.expires))
        return {action::expire, invalidate(reason::expiry)};
    if (!published_ && now >= acquisition_deadline_)
        return {action::acquisition_failed, invalidate(reason::acquisition_timeout)};
    if (published_ && !pending_) {
        if (now >= current_.t2 && state_ != state::rebinding) {
            state_ = state::rebinding;
            return {action::rebind, false};
        }
        if (now >= current_.t1 && state_ == state::bound) {
            state_ = state::renewing;
            return {action::renew, false};
        }
    }
    return {action::none, false};
}

bool lease_clock::usable(u64 now) const {
    return published_ && now >= last_now_ && now < current_.expires;
}
}
