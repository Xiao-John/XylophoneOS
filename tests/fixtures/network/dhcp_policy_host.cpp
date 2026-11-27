// SPDX-License-Identifier: Apache-2.0
// The production bounded parser and lease authorization run unchanged. The
// supplied clock is deterministic here; real lwIP/ACD/guest tests are separate.
#include "network/dhcp_policy.hpp"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

namespace {
using namespace xos;
using namespace xos::user::network::dhcp;
using bytes = std::vector<u8>;
constexpr u32 server = 0x0a000202, second_server = 0x0a000204;
constexpr u32 address = 0x0a00020f, resolver = 0x0a000203, second_resolver = 0x0a000205;
constexpr u32 xid = 0x12345678;
constexpr u64 start_time = 10 * second_ns;
void expect(bool condition, const char* description, int line = __builtin_LINE()) {
    if (!condition) { std::fprintf(stderr, "line %d: %s\n", line, description); std::abort(); }
}
void write_u32(u8* output, u32 value) {
    output[0] = static_cast<u8>(value >> 24); output[1] = static_cast<u8>(value >> 16);
    output[2] = static_cast<u8>(value >> 8); output[3] = static_cast<u8>(value);
}
policy trusted() {
    return {0x0a000200, 0xffffff00, 0x0a00020a, 0x0a0002c8,
            {server, second_server}, 2, {server, second_server}, 2,
            {resolver, second_resolver}, 2, 86400};
}
reply_context context(phase value = phase::requesting, u32 transaction = xid) {
    return {value, transaction, {0x52, 0x54, 0, 0x12, 0x34, 0x56},
            value == phase::selecting ? 0 : server, value == phase::selecting ? 0 : address};
}
void option(bytes& packet, u8 code, const bytes& data) {
    if (!packet.empty() && packet.back() == 255) packet.pop_back();
    packet.push_back(code); packet.push_back(static_cast<u8>(data.size()));
    packet.insert(packet.end(), data.begin(), data.end()); packet.push_back(255);
}
void option_u32(bytes& packet, u8 code, u32 value) {
    bytes data(4); write_u32(data.data(), value); option(packet, code, data);
}
usize option_offset(const bytes& packet, u8 code) {
    for (usize offset = 240; offset < packet.size();) {
        if (packet[offset] == code) return offset;
        if (packet[offset] == 255) break;
        if (!packet[offset]) { ++offset; continue; }
        offset += 2 + packet[offset + 1];
    }
    std::abort();
}
void remove_option(bytes& packet, u8 code) {
    const usize offset = option_offset(packet, code);
    packet.erase(packet.begin() + offset, packet.begin() + offset + 2 + packet[offset + 1]);
}
void replace_u32(bytes& packet, u8 code, u32 value) {
    write_u32(packet.data() + option_offset(packet, code) + 2, value);
}
bytes packet(message_type type = message_type::ack, u32 transaction = xid, u32 peer = server,
             u32 lease_seconds = 16) {
    bytes result(240);
    result[0] = 2; result[1] = 1; result[2] = 6;
    write_u32(result.data() + 4, transaction);
    write_u32(result.data() + 16, type == message_type::nak ? 0 : address);
    const reply_context identity = context();
    std::copy(identity.mac, identity.mac + 6, result.begin() + 28);
    write_u32(result.data() + 236, 0x63825363);
    option(result, 53, {static_cast<u8>(type)});
    option_u32(result, 54, peer);
    if (type != message_type::nak) {
        option_u32(result, 51, lease_seconds); option_u32(result, 1, 0xffffff00);
        option_u32(result, 3, server); option_u32(result, 6, resolver);
    }
    return result;
}
reply parsed(const bytes& data, reply_context expected = context(), policy authority = trusted(),
             u32 source = server) {
    reply result{};
    expect(validate_reply(data.data(), static_cast<u32>(data.size()), source, 67, expected, authority, result) == error::none,
           "valid packet admitted");
    return result;
}
void rejected(const bytes& data, reply_context expected = context(), policy authority = trusted(),
              u32 source = server, u16 port = 67) {
    reply output;
    std::memset(&output, 0xa5, sizeof(output));
    const reply original = output;
    expect(validate_reply(data.data(), static_cast<u32>(data.size()), source, port, expected, authority, output) != error::none,
           "invalid packet rejected");
    expect(std::memcmp(&output, &original, sizeof(output)) == 0, "rejection never partially updates output");
}
u64 bind(lease_clock& clock, u32 seconds = 16, u64 sent = start_time, u32 transaction = xid) {
    expect(clock.start(sent, sent + 30 * second_ns) == error::none, "start bounded acquisition");
    expect(clock.note_request_sent(phase::requesting, transaction, sent) == error::none, "actual REQUEST recorded");
    candidate_result candidate{};
    expect(clock.accept_ack(parsed(packet(message_type::ack, transaction, server, seconds), context(phase::requesting, transaction)),
                            sent + 1, candidate) == error::none, "ACK staged");
    expect(candidate.needs_acd && candidate.configuration_changed && !clock.usable(sent + 1), "ACD gates first address");
    bool changed = false;
    expect(clock.approve_address(candidate.generation, sent + 2, changed) == error::none && changed, "clear ACD publishes");
    return candidate.generation;
}

void policy_bounds() {
    expect(validate_policy(trusted()) == error::none, "trusted finite policy");
    for (u32 mask : {0u, 0xffffffffu, 0xfffffffeu, 0xffff00ffu}) {
        auto value = trusted(); value.mask = mask; expect(validate_policy(value) != error::none, "invalid mask");
    }
    auto value = trusted(); value.subnet |= 1; expect(validate_policy(value) != error::none, "canonical subnet");
    value = trusted(); value.first_address = value.last_address + 1; expect(validate_policy(value) != error::none, "ordered range");
    value = trusted(); value.first_address = value.subnet; expect(validate_policy(value) != error::none, "network not a lease");
    value = trusted(); value.last_address = value.subnet | ~value.mask; expect(validate_policy(value) != error::none, "broadcast not a lease");
    value = trusted(); value.server_count = 3; expect(validate_policy(value) != error::none, "bounded list");
    value = trusted(); value.server_count = 0; expect(validate_policy(value) != error::none, "server required");
    value = trusted(); value.servers[1] = value.servers[0]; expect(validate_policy(value) != error::none, "no duplicate authority");
    value = trusted(); value.resolver_count = 1; expect(validate_policy(value) != error::none, "unused list tail zero");
    value = trusted(); value.servers[0] = 0x0b000202; expect(validate_policy(value) != error::none, "direct server in subnet");
    value = trusted(); value.resolvers[0] = address; expect(validate_policy(value) != error::none, "lease range excludes infrastructure");
    value = trusted(); value.max_lease_seconds = 0; expect(validate_policy(value) != error::none, "nonzero lease cap");
    value.max_lease_seconds = ~u32{0}; expect(validate_policy(value) != error::none, "finite lease cap");
}

void valid_messages() {
    const auto ack = parsed(packet());
    expect(ack.address == address && ack.server == server && ack.gateway == server &&
           ack.mask == 0xffffff00 && ack.resolvers[0] == resolver && ack.lease_seconds == 16, "exact parsed configuration");
    expect(parsed(packet(message_type::offer), context(phase::selecting)).type == message_type::offer, "offer only selecting");
    expect(parsed(packet(message_type::nak)).type == message_type::nak, "authenticated NAK");
    auto data = packet(); option(data, 61, {1, 0x52, 0x54, 0, 0x12, 0x34, 0x56});
    option(data, 200, {}); data.push_back(0); parsed(data);
    auto authority = trusted(); authority.gateway_count = authority.resolver_count = 0;
    authority.gateways[0] = authority.gateways[1] = authority.resolvers[0] = authority.resolvers[1] = 0;
    data = packet(); remove_option(data, 3); remove_option(data, 6);
    const auto isolated = parsed(data, context(), authority);
    expect(!isolated.gateway && !isolated.resolver_count, "explicit no-router no-resolver policy");
    rejected(packet(message_type::ack), context(phase::selecting));
    rejected(packet(message_type::offer));
    rejected(packet(message_type::nak), context(phase::selecting));
}

void header_identity() {
    const auto original = packet();
    for (usize offset : {0u, 1u, 2u, 3u, 4u, 10u, 11u, 24u, 28u, 33u, 34u, 43u, 236u, 239u}) {
        auto data = original; data[offset] ^= 1; rejected(data);
    }
    auto data = original; data[10] = 0x80; parsed(data);
    data = original; write_u32(data.data() + 12, address); rejected(data);
    parsed(data, context(phase::renewing));
    write_u32(data.data() + 12, address + 1); rejected(data, context(phase::renewing));
    data = packet(message_type::nak); write_u32(data.data() + 12, address); rejected(data, context(phase::renewing));
    rejected(original, context(), trusted(), server, 68);
    rejected(original, context(), trusted(), 0x0a000206);
    auto expected = context(); expected.mac[0] |= 1; rejected(original, expected);
    expected = context(); std::fill(expected.mac, expected.mac + 6, 0); rejected(original, expected);
    expected = context(); expected.state = static_cast<phase>(99); rejected(original, expected);
    expected = context(phase::selecting); expected.selected_server = server; rejected(packet(message_type::offer), expected);
    data = original; option(data, 61, {1, 0x52, 0x54, 0, 0x12, 0x34, 0x57}); rejected(data);
    data = original; option(data, 61, {2, 0x52, 0x54, 0, 0x12, 0x34, 0x56}); rejected(data);
}

void server_authority() {
    auto data = packet(message_type::ack, xid, second_server);
    rejected(data, context(), trusted(), second_server);
    rejected(data, context(phase::renewing), trusted(), second_server);
    parsed(data, context(phase::rebinding), trusted(), second_server);
    rejected(data, context(phase::rebinding), trusted(), server);
    data = packet(message_type::nak, xid, second_server);
    rejected(data, context(), trusted(), second_server);
    parsed(data, context(phase::rebinding), trusted(), second_server);
    data = packet(message_type::offer, xid, second_server);
    parsed(data, context(phase::selecting), trusted(), second_server);
    auto expected = context(phase::rebinding); expected.xid ^= 1;
    rejected(packet(message_type::nak), expected);
    data = packet(message_type::nak); option_u32(data, 51, 10); rejected(data);
    data = packet(message_type::nak); write_u32(data.data() + 16, address); rejected(data);
}

void option_framing() {
    const auto original = packet();
    for (usize length = 0; length < original.size(); ++length)
        rejected(bytes(original.begin(), original.begin() + length));
    auto data = original; data.resize(reply_limit, 0); parsed(data);
    data.push_back(0); rejected(data);
    reply output{};
    expect(validate_reply(nullptr, 300, server, 67, context(), trusted(), output) == error::argument, "null is bounded");
    for (u8 code : {1, 3, 6, 51, 53, 54}) {
        data = original; const usize offset = option_offset(data, code);
        const bytes value(data.begin() + offset + 2, data.begin() + offset + 2 + data[offset + 1]);
        option(data, code, value); rejected(data);
        data = original; data[offset + 1] = 255; rejected(data);
    }
    for (u8 code : {33, 52, 121, 249}) { data = original; option(data, code, {1}); rejected(data); }
    data = original; option(data, 200, {}); option(data, 200, {}); rejected(data);
    data = original; data.push_back(1); rejected(data);
    data = original; data.pop_back(); data.push_back(200); rejected(data);
    data = original; data.pop_back(); data.push_back(200); data.push_back(2); data.push_back(1); rejected(data);
    data = original; remove_option(data, 53); rejected(data);
    data = original; remove_option(data, 54); rejected(data);
    data = original; remove_option(data, 1); option_u32(data, 1, 0xffffff00); rejected(data);
    data = original; remove_option(data, 3); option(data, 3, {10, 0, 2, 2, 10, 0, 2, 4}); rejected(data);
    data = original; remove_option(data, 6); option(data, 6, {10, 0, 2, 3, 10, 0, 2, 3}); rejected(data);
    data = original; remove_option(data, 6); option(data, 6, {}); rejected(data);
    data = original; remove_option(data, 6); option(data, 6, {10, 0, 2}); rejected(data);
    data = original; remove_option(data, 6); option(data, 6, {10, 0, 2, 3, 10, 0, 2, 5});
    expect(parsed(data).resolver_count == 2, "two admitted resolver addresses");
    data = original; option(data, 61, {1, 2}); rejected(data);
}

void configuration_and_timers() {
    for (u32 value : {0u, 0x0a000200u, 0x0a0002ffu, 0x0b00020fu, server, resolver, address + 1}) {
        auto data = packet(); write_u32(data.data() + 16, value); rejected(data);
    }
    for (u8 code : {1, 3, 6}) {
        auto data = packet(); replace_u32(data, code, 0x01020304); rejected(data);
        data = packet(); remove_option(data, code); rejected(data);
    }
    rejected(packet(message_type::ack, xid, server, 0));
    rejected(packet(message_type::ack, xid, server, ~u32{0}));
    rejected(packet(message_type::ack, xid, server, 86401));
    for (const auto values : {std::pair<u32, u32>{0, 14}, {8, 0}, {14, 8}, {8, 8}, {8, 16}, {16, 17}}) {
        auto data = packet(); option_u32(data, 58, values.first); option_u32(data, 59, values.second); rejected(data);
    }
    auto data = packet(); option_u32(data, 58, 8); option_u32(data, 59, 14);
    expect(parsed(data).has_t1 && parsed(data).has_t2, "explicit timers valid");
    parsed(packet(message_type::ack, xid, server, 1));
    auto authority = trusted(); authority.max_lease_seconds = ~u32{0} - 1;
    parsed(packet(message_type::ack, xid, server, ~u32{0} - 1), context(), authority);
}

void actual_request_and_acd() {
    lease_clock clock;
    expect(clock.start(start_time, start_time + 30 * second_ns) == error::none, "acquisition begins");
    candidate_result candidate{};
    expect(clock.accept_ack(parsed(packet()), start_time, candidate) == error::state, "ACK before actual REQUEST rejected");
    expect(clock.note_request_sent(phase::requesting, xid, start_time) == error::none, "actual first send");
    expect(clock.note_request_sent(phase::requesting, xid, start_time + second_ns) == error::none, "retransmit observed");
    auto ack = parsed(packet()); ack.xid ^= 1;
    expect(clock.accept_ack(ack, start_time + 2 * second_ns, candidate) == error::identity, "ACK xid tied to successful send");
    expect(clock.accept_ack(parsed(packet()), start_time + 2 * second_ns, candidate) == error::none, "delayed ACK staged");
    expect(clock.candidate().request_sent == start_time && clock.candidate().expires == start_time + 16 * second_ns,
           "retransmit and ACK delay do not extend lease");
    expect(!clock.usable(start_time + 2 * second_ns) && candidate.needs_acd, "ACK is not usable until ACD");
    bool changed = false;
    expect(clock.approve_address(candidate.generation + 1, start_time + 3 * second_ns, changed) == error::state, "wrong ACD generation rejected");
    expect(clock.approve_address(candidate.generation, start_time + 3 * second_ns, changed) == error::none && changed,
           "matching ACD publishes");
    expect(clock.usable(start_time + 3 * second_ns), "approved address usable");
    expect(clock.approve_address(candidate.generation, start_time + 3 * second_ns, changed) == error::state, "ACD completion one-shot");
    expect(clock.start(start_time + 3 * second_ns, start_time + 4 * second_ns) == error::state, "new acquisition cannot silently replace a published epoch");
}

void exact_deadlines_and_loss() {
    lease_clock clock; bind(clock);
    expect(clock.advance(start_time + 8 * second_ns - 1).next == action::none, "before T1");
    expect(clock.advance(start_time + 8 * second_ns).next == action::renew, "exact T1 renew");
    expect(clock.advance(start_time + 8 * second_ns).next == action::none, "renew edge once");
    expect(clock.note_request_sent(phase::renewing, xid, start_time + 8 * second_ns) == error::identity, "fresh renewal XID required");
    expect(clock.note_request_sent(phase::renewing, xid + 1, start_time + 8 * second_ns) == error::none, "renew request");
    expect(clock.advance(start_time + 14 * second_ns).next == action::rebind, "exact T2 rebind");
    expect(clock.note_request_sent(phase::rebinding, xid + 1, start_time + 14 * second_ns) == error::none, "broadcast request");
    expect(clock.current().expires == start_time + 16 * second_ns, "requests alone never renew");
    expect(clock.usable(start_time + 16 * second_ns - 1), "last valid nanosecond");
    expect(!clock.usable(start_time + 16 * second_ns), "expiry strict even before poll");
    const auto expired = clock.advance(start_time + 16 * second_ns);
    expect(expired.next == action::expire && expired.revoke && clock.last_reason() == reason::expiry, "expiry revokes epoch");
    expect(clock.advance(start_time + 16 * second_ns).next == action::none, "expiry only once");
    candidate_result ignored{};
    expect(clock.accept_ack(parsed(packet(message_type::ack, xid + 1), context(phase::rebinding, xid + 1)),
                            start_time + 17 * second_ns, ignored) == error::state, "late ACK cannot revive expired lease");
    lease_clock paused; bind(paused);
    const auto pause = paused.advance(start_time + 1000 * second_ns);
    expect(pause.next == action::expire && pause.revoke, "long pause expires before sending renewal");
}

void renewal_and_configuration() {
    lease_clock clock; bind(clock);
    const u64 renewed_at = start_time + 8 * second_ns;
    expect(clock.advance(renewed_at).next == action::renew, "renew transition");
    expect(clock.note_request_sent(phase::renewing, xid + 1, renewed_at) == error::none, "fresh renew sent");
    expect(clock.advance(start_time + 14 * second_ns).next == action::rebind, "lost renew leads broadcast");
    expect(clock.note_request_sent(phase::rebinding, xid + 1, start_time + 14 * second_ns) == error::none, "same transaction rebind");
    candidate_result candidate{};
    auto ack = parsed(packet(message_type::ack, xid + 1, second_server), context(phase::rebinding, xid + 1), trusted(), second_server);
    expect(clock.accept_ack(ack, start_time + 15 * second_ns, candidate) == error::none, "new admitted server renews");
    expect(clock.candidate().request_sent == renewed_at && clock.candidate().expires == renewed_at + 16 * second_ns,
           "rebind retains earliest ambiguous request time");
    expect(!candidate.needs_acd && !candidate.configuration_changed, "same effective configuration keeps epoch");
    bool changed = true;
    expect(clock.approve_address(candidate.generation, start_time + 15 * second_ns, changed) == error::none && !changed,
           "same address previously passed ACD");
    const u64 next_request = renewed_at + 8 * second_ns;
    expect(clock.note_request_sent(phase::renewing, xid + 2, next_request) == error::none, "next renew begins");
    auto data = packet(message_type::ack, xid + 2); replace_u32(data, 6, second_resolver); replace_u32(data, 3, second_server);
    ack = parsed(data, context(phase::renewing, xid + 2));
    expect(clock.accept_ack(ack, next_request + 1, candidate) == error::none && candidate.configuration_changed && !candidate.needs_acd,
           "route and resolver change requires epoch update");
    expect(clock.approve_address(candidate.generation, next_request + 2, changed) == error::none && changed, "configuration change surfaced");
}

void invalidation_and_generation() {
    for (reason cause : {reason::nak, reason::conflict, reason::link_lost, reason::stopped}) {
        lease_clock clock; bind(clock);
        expect(clock.invalidate(cause), "published invalidation revokes");
        expect(!clock.usable(start_time + second_ns) && !clock.has_candidate() && clock.last_reason() == cause,
               "invalidated state has no usable address or candidate");
        expect(!clock.invalidate(cause), "repeated invalidation has no second epoch");
    }
    lease_clock clock;
    expect(clock.start(start_time, start_time + 30 * second_ns) == error::none, "first start");
    expect(clock.note_request_sent(phase::requesting, xid, start_time) == error::none, "first request");
    candidate_result first{}, next{};
    expect(clock.accept_ack(parsed(packet()), start_time + 1, first) == error::none, "first candidate");
    expect(!clock.invalidate(reason::conflict), "unpublished conflict does not revoke existing epoch");
    expect(clock.start(start_time + 2, start_time + 30 * second_ns) == error::none, "explicit retry");
    expect(clock.note_request_sent(phase::requesting, xid + 1, start_time + 2) == error::none, "second request");
    expect(clock.accept_ack(parsed(packet(message_type::ack, xid + 1), context(phase::requesting, xid + 1)), start_time + 3, next) == error::none,
           "second candidate");
    bool changed = false;
    expect(next.generation != first.generation && clock.approve_address(first.generation, start_time + 4, changed) == error::state,
           "late ACD callback cannot authorize another acquisition");
    expect(clock.approve_address(next.generation, start_time + 4, changed) == error::none, "current generation approves");
}

void nak_and_late_ack() {
    lease_clock clock; bind(clock);
    const u64 renew_at = start_time + 8 * second_ns;
    expect(clock.advance(renew_at).next == action::renew, "renew edge before actual send");
    auto nak = parsed(packet(message_type::nak, xid + 1), context(phase::renewing, xid + 1));
    bool revoke = false;
    expect(clock.accept_nak(nak, renew_at, revoke) == error::state && !revoke && clock.usable(renew_at),
           "NAK for unsent request cannot revoke lease");
    expect(clock.note_request_sent(phase::renewing, xid + 1, renew_at) == error::none, "renew sent");
    nak.xid ^= 1;
    expect(clock.accept_nak(nak, renew_at + 1, revoke) == error::identity && clock.usable(renew_at + 1),
           "NAK xid matches actual request");
    nak.xid ^= 1;
    expect(clock.accept_nak(nak, renew_at + 2, revoke) == error::none && revoke && clock.last_reason() == reason::nak,
           "matching NAK revokes published lease");
    expect(clock.accept_nak(nak, renew_at + 3, revoke) == error::state, "repeated NAK cannot mutate a retired transaction");
    lease_clock late;
    expect(late.start(start_time, start_time + 30 * second_ns) == error::none, "late ACK acquisition");
    expect(late.note_request_sent(phase::requesting, xid, start_time) == error::none, "late ACK request");
    candidate_result candidate{42, true, true};
    const auto ack = parsed(packet(message_type::ack, xid, server, 1));
    expect(late.accept_ack(ack, start_time + second_ns, candidate) == error::expired && candidate.generation == 42 &&
           !late.has_candidate() && !late.usable(start_time + second_ns), "already expired ACK fails without publication or output mutation");
    lease_clock old; bind(old);
    expect(old.note_request_sent(phase::renewing, xid + 1, renew_at) == error::none, "old lease renew");
    expect(old.accept_ack(parsed(packet(message_type::ack, xid + 1), context(phase::renewing, xid + 1)),
                          start_time + 16 * second_ns, candidate) == error::expired,
           "renew ACK after old expiry cannot revive even if advance not yet called");
}

void short_lease_and_acquisition() {
    lease_clock clock; bind(clock, 1);
    expect(clock.current().t1 == start_time + second_ns / 2 && clock.current().t2 == start_time + second_ns * 7 / 8,
           "sub-minute default timers retain fractional seconds");
    expect(clock.advance(start_time + second_ns * 7 / 8).next == action::rebind, "pause beyond T1 goes straight to rebind");
    expect(clock.advance(start_time + second_ns).revoke, "one-second lease expires exactly");
    for (u64 deadline : {start_time, start_time - 1, ~u64{0}, start_time + acquisition_limit_ns + 1}) {
        lease_clock invalid;
        expect(invalid.start(start_time, deadline) == error::timing, "acquisition must have finite bounded future deadline");
    }
    lease_clock acquiring;
    expect(acquiring.start(start_time, start_time + second_ns) == error::none, "short acquisition");
    const auto timeout = acquiring.advance(start_time + second_ns);
    expect(timeout.next == action::acquisition_failed && !timeout.revoke && acquiring.current_state() == state::failed,
           "lost acquisition stops instead of unbounded retry");
    lease_clock checking;
    expect(checking.start(start_time, start_time + 30 * second_ns) == error::none, "ACD expiry start");
    expect(checking.note_request_sent(phase::requesting, xid, start_time) == error::none, "ACD expiry request");
    candidate_result candidate{};
    expect(checking.accept_ack(parsed(packet(message_type::ack, xid, server, 1)), start_time + 1, candidate) == error::none, "short ACK");
    bool changed = false;
    expect(checking.approve_address(candidate.generation, start_time + second_ns, changed) == error::expired, "ACD completing at expiry cannot publish");
    const auto expired = checking.advance(start_time + second_ns);
    expect(expired.next == action::expire && !expired.revoke && !checking.usable(start_time + second_ns), "unpublished short candidate expires");
}

void time_width_and_regression() {
    lease_clock zero; bind(zero, 1, 0);
    expect(zero.current().request_sent == 0 && zero.current().expires == second_ns, "zero is a real REQUEST timestamp");
    const u64 max = ~u64{0}, request = max - 2 * second_ns;
    auto exercise = [&](u32 duration, error expected) {
        lease_clock clock;
        expect(clock.start(request, max - 1) == error::none, "full-width acquisition");
        expect(clock.note_request_sent(phase::requesting, xid, request) == error::none, "full-width request");
        candidate_result candidate{};
        expect(clock.accept_ack(parsed(packet(message_type::ack, xid, server, duration)), request + 1, candidate) == expected,
               "addition overflow checked");
        if (expected == error::none) {
            expect(clock.candidate().expires == max, "finite exact-u64-max expiry represented");
            bool changed = false;
            expect(clock.approve_address(candidate.generation, request + 2, changed) == error::none, "full-width publish");
            expect(clock.advance(max).revoke, "full-width expiry handled");
        }
    };
    exercise(2, error::none); exercise(3, error::overflow);
    lease_clock wide;
    expect(wide.start(0, acquisition_limit_ns) == error::none, "large lease starts");
    expect(wide.note_request_sent(phase::requesting, xid, 0) == error::none, "large lease request");
    auto authority = trusted(); authority.max_lease_seconds = ~u32{0} - 1;
    candidate_result candidate{};
    expect(wide.accept_ack(parsed(packet(message_type::ack, xid, server, ~u32{0} - 1), context(), authority), 1, candidate) == error::none,
           "large finite defaults avoid overflow");
    const u64 duration = static_cast<u64>(~u32{0} - 1) * second_ns;
    expect(wide.candidate().expires == duration && wide.candidate().t2 == (duration / 8) * 7, "wide timer values exact");
    lease_clock backwards; bind(backwards);
    expect(!backwards.usable(start_time), "regressed time not usable");
    const auto failed = backwards.advance(start_time);
    expect(failed.next == action::clock_failed && failed.revoke && backwards.last_reason() == reason::clock_failure,
           "monotonic regression fails closed");
}

void bounded_mutations() {
    const auto original = packet();
    u32 random = 0x89abcdef;
    for (u32 round = 0; round < 20000; ++round) {
        random ^= random << 13; random ^= random >> 17; random ^= random << 5;
        bytes data = original;
        if (round % 3 == 0) data.resize(random % (reply_limit + 8), static_cast<u8>(random));
        if (!data.empty()) data[(random >> 10) % data.size()] ^= static_cast<u8>((random >> 24) | 1);
        reply output;
        std::memset(&output, 0xa5, sizeof(output));
        const reply before = output;
        const auto result = validate_reply(data.data(), static_cast<u32>(data.size()), server, 67, context(), trusted(), output);
        if (result != error::none) expect(!std::memcmp(&output, &before, sizeof(output)), "mutation failure atomic");
        else expect(output.xid == xid && output.server == server && output.address == address && output.mask == 0xffffff00 &&
                    output.gateway == server && output.resolvers[0] == resolver && output.lease_seconds > 0 && output.lease_seconds <= 86400,
                    "successful mutation retains admitted authority");
    }
}

struct scenario { const char* name; void (*run)(); };
const scenario scenarios[] = {
    {"policy_bounds", policy_bounds}, {"valid_messages", valid_messages},
    {"header_identity", header_identity}, {"server_authority", server_authority},
    {"option_framing", option_framing}, {"configuration_and_timers", configuration_and_timers},
    {"actual_request_and_acd", actual_request_and_acd}, {"exact_deadlines_and_loss", exact_deadlines_and_loss},
    {"renewal_and_configuration", renewal_and_configuration}, {"invalidation_and_generation", invalidation_and_generation},
    {"nak_and_late_ack", nak_and_late_ack},
    {"short_lease_and_acquisition", short_lease_and_acquisition}, {"time_width_and_regression", time_width_and_regression},
    {"bounded_mutations", bounded_mutations}
};
}
int main(int argc, char** argv) {
    if (argc != 2) return 2;
    if (!std::strcmp(argv[1], "--list")) {
        for (const auto& value : scenarios) std::puts(value.name);
        return 0;
    }
    for (const auto& value : scenarios) if (!std::strcmp(argv[1], value.name)) {
        value.run(); std::printf("DHCP_POLICY_SCENARIO_PASSED=%s\n", value.name); return 0;
    }
    return 2;
}
