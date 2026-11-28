// SPDX-License-Identifier: Apache-2.0
// Production lwIP and service_core run against a packet-level peer. No socket
// or PCB callbacks are replaced by simulated transport outcomes.
#include "network/lwip_stack.hpp"
#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <map>
#include <vector>
extern "C" {
#include "lwip/memp.h"
}

namespace {
using namespace xos;
using namespace xos::net2;
using namespace xos::user::network;
using bytes = std::vector<u8>;
constexpr std::array<u8, 6> local_mac{0x52, 0x54, 0x00, 0x12, 0x34, 0x56};
constexpr std::array<u8, 6> remote_mac{0x52, 0x54, 0x00, 0x65, 0x43, 0x21};
constexpr u32 local_address = 0x0a00020f;
constexpr u8 fin_bit = 1, syn_bit = 2, rst_bit = 4, psh_bit = 8, ack_bit = 16;
void expect(bool value, const char* description, int line = __builtin_LINE()) {
    if (!value) { std::fprintf(stderr, "line %d: %s\n", line, description); std::abort(); }
}
u16 read_u16(const u8* value) { return static_cast<u16>((value[0] << 8) | value[1]); }
u32 read_u32(const u8* value) {
    return (static_cast<u32>(value[0]) << 24) | (static_cast<u32>(value[1]) << 16) |
           (static_cast<u32>(value[2]) << 8) | value[3];
}
void write_u16(u8* value, u16 number) { value[0] = number >> 8; value[1] = number; }
void write_u32(u8* value, u32 number) {
    value[0] = number >> 24; value[1] = number >> 16; value[2] = number >> 8; value[3] = number;
}
u16 checksum(const u8* data, usize length, u32 sum = 0) {
    for (usize i = 0; i + 1 < length; i += 2) sum += read_u16(data + i);
    if (length & 1) sum += static_cast<u32>(data[length - 1]) << 8;
    while (sum >> 16) sum = (sum & 65535) + (sum >> 16);
    return static_cast<u16>(~sum);
}
u32 pseudo_sum(u32 from, u32 to, u8 transport, u16 length) {
    return (from >> 16) + (from & 65535) + (to >> 16) + (to & 65535) + transport + length;
}
bytes pattern(usize length, u32 offset = 0) {
    bytes value(length);
    for (usize i = 0; i < length; ++i) value[i] = static_cast<u8>((i + offset) * 37 + 11);
    return value;
}
struct packet_peer {
    struct tcp_peer {
        u16 local_port = 0, remote_port = 0;
        u32 client_next = 0, peer_next = 0;
        bytes client_data;
    };
    std::deque<bytes> input;
    std::vector<bytes> output, udp_payloads;
    std::map<u16, tcp_peer> connections;
    u64 now = 1'000'000'000ull, received_frame_advance = 0;
    u32 random_state = 0x9712ab41, tcp_syn_count = 0, tcp_fin_count = 0, tcp_rst_count = 0;
    u16 udp_local_port = 0, udp_remote_port = 0;
    bool answer_arp = true, answer_syn = true, answer_data = true, echo_tcp = true, echo_udp = true;
    bool answer_fin = true;
    bool transmit_blocked = false, transmit_failed = false, clock_failed = false, random_failed = false;
    bytes ethernet(u16 type, usize body_length) {
        bytes frame(14 + body_length);
        std::copy(local_mac.begin(), local_mac.end(), frame.begin());
        std::copy(remote_mac.begin(), remote_mac.end(), frame.begin() + 6);
        write_u16(frame.data() + 12, type); return frame;
    }
    bytes ipv4(u8 transport, usize body_length) {
        auto frame = ethernet(0x0800, 20 + body_length); auto* ip = frame.data() + 14;
        ip[0] = 0x45; write_u16(ip + 2, static_cast<u16>(20 + body_length));
        ip[8] = 64; ip[9] = transport;
        write_u32(ip + 12, permitted_address); write_u32(ip + 16, local_address);
        write_u16(ip + 10, checksum(ip, 20)); return frame;
    }
    void arp_reply() {
        auto frame = ethernet(0x0806, 28); auto* arp = frame.data() + 14;
        write_u16(arp, 1); write_u16(arp + 2, 0x0800); arp[4] = 6; arp[5] = 4; write_u16(arp + 6, 2);
        std::copy(remote_mac.begin(), remote_mac.end(), arp + 8); write_u32(arp + 14, permitted_address);
        std::copy(local_mac.begin(), local_mac.end(), arp + 18); write_u32(arp + 24, local_address);
        input.push_back(std::move(frame));
    }
    void tcp_packet(tcp_peer& connection, u8 flags, const bytes& payload = {}) {
        auto frame = ipv4(6, 20 + payload.size()); auto* tcp = frame.data() + 34;
        write_u16(tcp, connection.remote_port); write_u16(tcp + 2, connection.local_port);
        write_u32(tcp + 4, connection.peer_next); write_u32(tcp + 8, connection.client_next);
        tcp[12] = 0x50; tcp[13] = flags; write_u16(tcp + 14, 65535);
        std::copy(payload.begin(), payload.end(), tcp + 20);
        write_u16(tcp + 16, checksum(tcp, 20 + payload.size(),
            pseudo_sum(permitted_address, local_address, 6, static_cast<u16>(20 + payload.size()))));
        connection.peer_next += static_cast<u32>(payload.size()) + !!(flags & syn_bit) + !!(flags & fin_bit);
        input.push_back(std::move(frame));
    }
    void udp_packet(const bytes& payload, u16 source_port = 0) {
        expect(udp_local_port != 0, "UDP peer observed local port");
        auto frame = ipv4(17, 8 + payload.size()); auto* udp = frame.data() + 34;
        write_u16(udp, source_port ? source_port : udp_remote_port); write_u16(udp + 2, udp_local_port);
        write_u16(udp + 4, static_cast<u16>(8 + payload.size()));
        std::copy(payload.begin(), payload.end(), udp + 8);
        const u16 checked = checksum(udp, 8 + payload.size(),
            pseudo_sum(permitted_address, local_address, 17, static_cast<u16>(8 + payload.size())));
        write_u16(udp + 6, checked ? checked : 65535); input.push_back(std::move(frame));
    }
    void observe(const u8* frame, u32 length) {
        expect(length >= 14, "outbound Ethernet header"); const u16 type = read_u16(frame + 12);
        if (type == 0x0806) {
            expect(length >= 42, "outbound ARP length");
            if (answer_arp && read_u16(frame + 20) == 1 && read_u32(frame + 38) == permitted_address) arp_reply();
            return;
        }
        if (type != 0x0800) return;
        expect(length >= 34, "outbound IPv4 header"); const auto* ip = frame + 14;
        const u32 header = (ip[0] & 15) * 4, total = read_u16(ip + 2);
        expect(header >= 20 && total >= header && length >= 14 + total, "outbound IPv4 bounds");
        expect(checksum(ip, header) == 0, "outbound IPv4 checksum");
        expect(read_u32(ip + 12) == local_address && read_u32(ip + 16) == permitted_address, "outbound address pair");
        const auto* body = ip + header; const u32 body_length = total - header;
        if (ip[9] == 17) {
            expect(body_length >= 8 && read_u16(body + 4) == body_length, "outbound UDP bounds");
            expect(checksum(body, body_length, pseudo_sum(local_address, permitted_address, 17,
                   static_cast<u16>(body_length))) == 0, "outbound UDP checksum");
            udp_local_port = read_u16(body); udp_remote_port = read_u16(body + 2);
            udp_payloads.emplace_back(body + 8, body + body_length);
            if (echo_udp) udp_packet(udp_payloads.back());
            return;
        }
        if (ip[9] != 6) return;
        expect(body_length >= 20, "outbound TCP header"); const u32 tcp_header = (body[12] >> 4) * 4;
        expect(tcp_header >= 20 && tcp_header <= body_length, "outbound TCP bounds");
        expect(checksum(body, body_length, pseudo_sum(local_address, permitted_address, 6,
               static_cast<u16>(body_length))) == 0, "outbound TCP checksum");
        const u16 local_port = read_u16(body), remote_port = read_u16(body + 2);
        auto& connection = connections[local_port];
        connection.local_port = local_port; connection.remote_port = remote_port;
        const u32 sequence = read_u32(body + 4); const u8 flags = body[13];
        if (flags & rst_bit) { ++tcp_rst_count; return; }
        if (flags & fin_bit) ++tcp_fin_count;
        if (flags & syn_bit) {
            ++tcp_syn_count; connection.client_next = sequence + 1;
            if (answer_syn) {
                connection.peer_next = 0x54321000u + local_port; tcp_packet(connection, syn_bit | ack_bit);
            }
            return;
        }
        const u32 payload_length = body_length - tcp_header;
        if (payload_length || (flags & fin_bit)) {
            const bool fresh = sequence == connection.client_next;
            if (fresh) {
                connection.client_next += payload_length + !!(flags & fin_bit);
                connection.client_data.insert(connection.client_data.end(), body + tcp_header, body + body_length);
            }
            if (answer_data) {
                bytes echoed;
                if (fresh && echo_tcp) echoed.assign(body + tcp_header, body + body_length);
                tcp_packet(connection, ack_bit | (echoed.empty() ? 0 : psh_bit) |
                           ((flags & fin_bit) && fresh && answer_fin ? fin_bit : 0), echoed);
            }
        }
    }
    frame_io callbacks() {
        return {this,
            [](void* context, u8* data, u32 capacity) -> i64 {
                auto& self = *static_cast<packet_peer*>(context);
                if (self.input.empty()) return 0;
                auto frame = std::move(self.input.front()); self.input.pop_front();
                self.now += self.received_frame_advance; self.received_frame_advance = 0;
                std::copy_n(frame.data(), std::min<usize>(frame.size(), capacity), data);
                return static_cast<i64>(frame.size()); },
            [](void* context, const u8* data, u32 length) -> i64 {
                auto& self = *static_cast<packet_peer*>(context);
                if (self.transmit_failed) return io;
                if (self.transmit_blocked) return would_block;
                self.output.emplace_back(data, data + length); self.observe(data, length); return 0; },
            [](void* context) -> i64 {
                auto& self = *static_cast<packet_peer*>(context);
                return self.clock_failed ? io : static_cast<i64>(self.now); },
            [](void* context, u32& value) -> i64 {
                auto& self = *static_cast<packet_peer*>(context);
                if (self.random_failed) return io;
                self.random_state ^= self.random_state << 13; self.random_state ^= self.random_state >> 17;
                self.random_state ^= self.random_state << 5; value = self.random_state; return 0; }};
    }
    tcp_peer& tcp_connection() {
        expect(connections.size() == 1, "one TCP peer"); return connections.begin()->second;
    }
};

struct environment {
    packet_peer peer;
    lwip_stack stack;
    service_core core;
    u64 sequences[session_limit]{};
    static constexpr u64 controller = 77;
    explicit environment(const egress_policy& policy = default_egress_policy) {
        expect(stack.initialize(peer.callbacks(), local_mac.data()) == 0, "initialize production lwIP");
        core.initialize(controller, stack.api(), {}, 0, policy); peer.output.clear();
    }
    ~environment() { core.shutdown(); stack.shutdown(); }
    u32 attach(u64 pid = 101) {
        const i64 slot = core.attach(pid, peer.now); expect(slot >= 0, "attach authenticated peer");
        sequences[slot] = 0; return static_cast<u32>(slot);
    }
    message input(u32 slot, operation action, u64 handle = 0) {
        message request{}; request.version = version; request.action = action;
        request.sequence = ++sequences[slot]; request.object = handle;
        request.deadline = peer.now + 5'000'000'000ull; return request;
    }
    message dispatch(u32 slot, const message& request) {
        message reply{};
        expect(core.dispatch(slot, request, header_bytes + request.length, peer.now, reply), "accept well-formed request");
        expect(reply.version == version && reply.sequence == request.sequence && reply.action == request.action,
               "reply envelope matches request");
        expect(!reply.deadline && !reply.reserved && !reply.address && !reply.port && reply.transport == protocol::none,
               "reply reserved fields cleared");
        expect(reply.length <= payload_bytes && (reply.result >= 0 || !reply.length), "reply payload bounds");
        return reply;
    }
    message request(u32 slot, operation action, u64 handle = 0) { return dispatch(slot, input(slot, action, handle)); }
    u64 open(u32 slot, protocol transport = protocol::udp, u16 port = 9000) {
        auto request = input(slot, operation::open); request.address = permitted_address;
        request.port = port; request.transport = transport; const auto reply = dispatch(slot, request);
        expect(reply.result == 0 && reply.object, "open connection"); return reply.object;
    }
    message send(u32 slot, u64 handle, const bytes& data) {
        expect(data.size() <= payload_bytes, "bounded request data");
        auto request = input(slot, operation::send, handle); request.length = static_cast<u32>(data.size());
        std::copy(data.begin(), data.end(), request.data); return dispatch(slot, request);
    }
    message receive(u32 slot, u64 handle, u32 capacity = payload_bytes) {
        auto request = input(slot, operation::receive, handle); request.flags = capacity; return dispatch(slot, request);
    }
    readiness_snapshot readiness(u32 slot, u64 handle) {
        const auto reply = request(slot, operation::readiness, handle);
        expect(reply.result == 0 && reply.length == sizeof(readiness_snapshot), "valid readiness response");
        readiness_snapshot snapshot{};
        std::memcpy(&snapshot, reply.data, sizeof(snapshot));
        expect(snapshot.generation && !snapshot.reserved && !(snapshot.events & ~ready_all), "bounded readiness snapshot");
        return snapshot;
    }
    void poll() { expect(stack.poll() == 0, "poll production lwIP"); }
    u64 connected_tcp(u32 slot) {
        const u64 handle = open(slot, protocol::tcp);
        expect(request(slot, operation::status, handle).flags == connecting, "TCP starts connecting");
        poll(); expect(request(slot, operation::status, handle).flags == connected, "real TCP handshake");
        expect(peer.tcp_syn_count == 1, "one TCP SYN"); return handle;
    }
};
void admission_and_stop() {
    environment env;
    expect(env.core.attach(0, env.peer.now) == closed, "zero PID rejected");
    const u32 first = env.attach();
    expect(env.core.attach(101, env.peer.now) == resources, "one session per PID");
    for (u64 pid = 102; pid < 105; ++pid) (void)env.attach(pid);
    expect(env.core.attach(105, env.peer.now) == resources, "ordinary session ceiling");
    const u32 controller = env.attach(environment::controller);
    expect(controller == client_sessions && env.core.session_count() == session_limit, "reserved controller admission");
    expect(env.request(first, operation::stop).result == denied, "only controller may stop");
    expect(!env.core.stopping(), "denied stop has no side effect");
    expect(env.request(controller, operation::stop).result == 0 && env.core.stopping(), "controller stops service");
    expect(env.core.attach(900, env.peer.now) == closed, "stop forbids admissions");
}
void framing_and_replay() {
    environment env;
    for (u32 mutation = 0; mutation < 9; ++mutation) {
        const u32 slot = env.attach(200 + mutation); auto input = env.input(slot, operation::information);
        message reply{}; u32 length = header_bytes;
        if (mutation == 0) input.version = 1;
        if (mutation == 1) input.reserved = 1;
        if (mutation == 2) input.result = -1;
        if (mutation == 3) input.length = payload_bytes + 1;
        if (mutation == 4) input.sequence = 0;
        if (mutation == 5) input.sequence = 2;
        if (mutation == 6) length = header_bytes - 1;
        if (mutation == 7) ++length;
        if (mutation == 8) (void)env.dispatch(slot, input);
        expect(!env.core.dispatch(slot, input, length, env.peer.now, reply), "malformed or replayed request rejected");
        env.core.detach(slot);
    }
    const u32 slot = env.attach(); auto input = env.input(slot, operation::information);
    input.action = static_cast<operation>(999);
    expect(env.dispatch(slot, input).result == unsupported, "unknown operation rejected without side effects");
    expect(env.core.connection_count() == 0, "malformed frames allocate nothing");
}
void address_policy() {
    environment env; const u32 slot = env.attach();
    for (const u32 address : {0u, 0x7f000001u, 0xffffffffu, 0xe0000001u, 0x0a000203u}) {
        auto input = env.input(slot, operation::open); input.transport = protocol::tcp;
        input.address = address; input.port = 80;
        expect(env.dispatch(slot, input).result == denied, "address denied before PCB allocation");
    }
    for (u32 mutation = 0; mutation < 3; ++mutation) {
        auto input = env.input(slot, operation::open); input.transport = protocol::udp;
        input.address = permitted_address; input.port = 80;
        if (mutation == 0) input.port = 0;
        if (mutation == 1) input.transport = protocol::none;
        if (mutation == 2) input.object = 1;
        expect(env.dispatch(slot, input).result == invalid, "invalid open rejected");
    }
    expect(env.core.connection_count() == 0 && env.peer.output.empty(), "denied requests cannot emit frames");
}
void trusted_egress_policy() {
    egress_policy policy{{{0x0a000200, 24, protocol::udp, 9000, 9000},
                          {0x0a000202, 32, protocol::udp, 67, 68}}, 2};
    environment env(policy); const u32 slot = env.attach();
    // The service snapshots installation authority; mutable caller storage is
    // not a way for subsequent network configuration to expand that grant.
    policy.rules[0].last_port = 65535;
    for (const auto rule : {egress_rule{0x0a000202, 32, protocol::udp, 9001, 9001},
                            egress_rule{0x0a000202, 32, protocol::tcp, 9000, 9000},
                            egress_rule{0x0a000301, 32, protocol::udp, 9000, 9000},
                            egress_rule{0x0a000202, 32, protocol::udp, 67, 67},
                            egress_rule{0x0a000202, 32, protocol::udp, 68, 68}}) {
        auto input = env.input(slot, operation::open); input.address = rule.network;
        input.transport = rule.transport; input.port = rule.first_port;
        expect(env.dispatch(slot, input).result == denied, "tuple denied by immutable installation policy");
    }
    expect(env.core.connection_count() == 0 && env.peer.output.empty(), "policy denial precedes PCB and frames");
    const auto handle = env.open(slot, protocol::udp, 9000);
    const auto data = pattern(43);
    expect(env.send(slot, handle, data).result == 43, "admitted tuple sends via real lwIP");
    env.poll(); const auto echoed = env.receive(slot, handle);
    expect(echoed.result == 0 && bytes(echoed.data, echoed.data + echoed.length) == data,
           "admitted policy tuple receives the real packet echo");
}
void invalid_egress_fails_closed() {
    environment env; const u32 slot = env.attach();
    for (u32 change = 0; change < 6; ++change) {
        auto policy = default_egress_policy;
        if (change == 0) policy.count = egress_rule_limit + 1;
        if (change == 1) policy.rules[0].prefix = 33;
        if (change == 2) policy.rules[0].prefix = 24;
        if (change == 3) policy.rules[0].transport = protocol::none;
        if (change == 4) policy.rules[0].first_port = 0;
        if (change == 5) { policy.rules[0].first_port = 90; policy.rules[0].last_port = 80; }
        expect(!valid_egress_policy(policy), "invalid trusted input detected");
        env.core.initialize(environment::controller, env.stack.api(), {}, 0, policy);
        auto input = env.input(slot, operation::open); input.address = permitted_address;
        input.transport = protocol::udp; input.port = 9000;
        expect(env.dispatch(slot, input).result == denied && !env.core.connection_count() && env.peer.output.empty(),
               "malformed policy does not retain a permissive default");
    }
    constexpr egress_policy all{{{0, 0, protocol::tcp, 1, 65535}}, 1};
    static_assert(valid_egress_policy(all));
    for (const u32 address : {0u, 0x7f000001u, 0xe0000001u, 0xffffffffu})
        expect(!egress_permitted(all, address, protocol::tcp, 80), "non-unicast addresses remain denied");
    expect(egress_permitted(all, 0xc0000201u, protocol::tcp, 80), "an explicit /0 is an explicit broad grant");
}
void object_isolation() {
    environment env; const u32 owner = env.attach(), other = env.attach(102); const u64 handle = env.open(owner);
    for (const auto action : {operation::status, operation::send, operation::receive, operation::close, operation::cancel}) {
        auto input = env.input(other, action, handle); if (action == operation::receive) input.flags = 32;
        expect(env.dispatch(other, input).result == denied, "cross-session handle rejected");
    }
    expect(env.core.connection_count() == 1, "foreign operations preserve owner resource");
    expect(env.request(owner, operation::cancel, handle).result == 0, "owner cancels");
    expect(env.request(owner, operation::status, handle).result == closed, "stale handle closed");
    const u64 replacement = env.open(owner); expect(replacement > handle, "handles are never reused");
}
void connection_quotas() {
    environment env; u32 owners[client_sessions];
    for (u32 i = 0; i < client_sessions; ++i) {
        owners[i] = env.attach(101 + i); (void)env.open(owners[i]); (void)env.open(owners[i]);
        auto input = env.input(owners[i], operation::open); input.address = permitted_address;
        input.port = 9; input.transport = protocol::udp;
        expect(env.dispatch(owners[i], input).result == resources, "per-session PCB quota");
    }
    expect(env.core.connection_count() == connection_limit, "global connection quota reached");
    const u32 controller = env.attach(environment::controller);
    auto input = env.input(controller, operation::open); input.address = permitted_address;
    input.port = 9; input.transport = protocol::udp;
    expect(env.dispatch(controller, input).result == resources, "global quota includes controller");
    env.core.detach(owners[0]); expect(env.core.connection_count() == 6, "detach releases all peer PCBs");
    (void)env.open(controller); (void)env.open(controller);
    env.core.shutdown(); expect(env.core.connection_count() == 0 && env.core.session_count() == 0, "shutdown releases service resources");
}
void revoke_policy() {
    environment env; const u32 owner = env.attach(), controller = env.attach(environment::controller);
    (void)env.open(owner); (void)env.open(owner);
    expect(env.request(owner, operation::revoke_peer, 102).result == denied, "only controller revokes");
    expect(env.request(controller, operation::revoke_peer, 101).result == 0, "controller revokes peer");
    expect(!env.core.alive(owner) && env.core.connection_count() == 0, "revoke closes all peer resources");
    expect(env.core.attach(101, env.peer.now) == denied, "revoked peer cannot reconnect");
    expect(env.request(controller, operation::revoke_peer, 101).result == 0, "repeat revoke is idempotent");
    expect(env.request(controller, operation::revoke_peer, environment::controller).result == invalid, "controller cannot revoke itself");
    for (u64 pid = 102; pid < 117; ++pid)
        expect(env.request(controller, operation::revoke_peer, pid).result == 0, "bounded revoke table entry");
    const u32 survivor = env.attach(117); (void)env.open(survivor);
    expect(env.request(controller, operation::revoke_peer, 117).result == resources, "full revoke table rejects atomically");
    expect(env.core.alive(survivor) && env.core.connection_count() == 1, "failed revoke preserves live session");
}
void deadlines_and_idle() {
    environment env; const u32 slot = env.attach(); const u64 initial = env.peer.now;
    for (const u64 deadline : {u64{0}, initial, initial - 1, initial + max_request_ns + 1}) {
        auto input = env.input(slot, operation::open); input.address = permitted_address;
        input.port = 9; input.transport = protocol::tcp; input.deadline = deadline;
        expect(env.dispatch(slot, input).result == timeout, "invalid request deadline rejected");
    }
    expect(env.core.connection_count() == 0 && env.peer.output.empty(), "expired requests allocate nothing");
    (void)env.open(slot); env.core.expire(initial - 1);
    expect(env.core.alive(slot), "backward sample cannot underflow idle duration");
    env.core.expire(initial + idle_ns - 1); expect(env.core.alive(slot), "idle boundary is exclusive before deadline");
    env.peer.now = initial + idle_ns - 1; (void)env.request(slot, operation::information);
    env.core.expire(initial + idle_ns); expect(env.core.alive(slot), "request refreshes idle timer");
    env.core.expire(env.peer.now + idle_ns);
    expect(!env.core.alive(slot) && env.core.connection_count() == 0, "idle expiry releases PCB");
}
void socket_capabilities_and_isolation() {
    environment env; const u32 owner = env.attach(), other = env.attach(102);
    const auto reply = env.request(owner, operation::capabilities);
    capability_snapshot capabilities{};
    expect(!reply.result && reply.length == sizeof(capabilities), "capability snapshot shape");
    std::memcpy(&capabilities, reply.data, sizeof(capabilities));
    expect(capabilities.revision == socket_extension_revision && !capabilities.reserved &&
           capabilities.flags == (capability_readiness | capability_shutdown_write), "explicit extension support");
    expect(env.request(owner, operation::capabilities, 1).result == invalid, "capabilities has no handle");
    const u64 handle = env.connected_tcp(owner);
    for (const auto action : {operation::readiness, operation::shutdown_write, operation::shutdown_read}) {
        expect(env.request(other, action, handle).result == denied, "extensions preserve handle ownership");
        auto malformed = env.input(owner, action, handle); malformed.flags = 1;
        expect(env.dispatch(owner, malformed).result == invalid, "extension flags must be zero");
    }
    expect(!env.peer.tcp_fin_count, "rejected shutdown emits no FIN");
    const u64 udp = env.open(owner);
    expect(env.request(owner, operation::readiness, udp).result == unsupported &&
           env.request(owner, operation::shutdown_write, udp).result == unsupported, "extension explicitly TCP only");
    expect(env.request(owner, operation::cancel, handle).result == 0, "cancel extended socket");
    expect(env.request(owner, operation::readiness, handle).result == closed, "stale snapshot handle rejected");
}
void readiness_page_and_read_shutdown() {
    environment env; const u32 owner = env.attach(), other = env.attach(102);
    env.core.enable_readiness_pages();
    auto query = env.input(owner, operation::capabilities); query.flags = capabilities_extended;
    auto reply = env.dispatch(owner, query); capability_snapshot features{};
    std::memcpy(&features, reply.data, sizeof(features));
    expect(!reply.result && features.revision == socket_extension_revision_2 && features.flags == 15,
           "v2 explicitly negotiates pages and read shutdown");
    expect(env.request(owner, operation::readiness_bind).result == 0, "authorized page binding");
    const u32 controller = env.attach(environment::controller);
    expect(env.request(controller, operation::readiness_bind).result == denied, "controller has no application page");
    const u64 handle = env.connected_tcp(owner); env.peer.echo_tcp = false;
    readiness_page page{};
    expect(env.core.capture_readiness(owner, page, env.peer.now) == 0 && page.count == 1 &&
           page.session_generation == env.core.generation(owner) && page.records[0].handle == handle &&
           page.records[0].ready.events == ready_write, "snapshot binds owner and live connection");
    expect(env.core.capture_readiness(other, page, env.peer.now) == 0 && page.count == 0,
           "other application cannot enumerate owner's connection");
    const auto incoming = pattern(37);
    env.peer.tcp_packet(env.peer.tcp_connection(), ack_bit | psh_bit, incoming); env.poll();
    expect(env.request(owner, operation::shutdown_read, handle).result == 0, "discard buffered receive bytes");
    expect(env.request(owner, operation::shutdown_read, handle).result == 0, "read shutdown idempotent");
    expect(!env.peer.tcp_rst_count && !env.peer.tcp_fin_count, "read shutdown never transmits RST or FIN");
    expect(env.receive(owner, handle).flags == eof, "local read returns EOF after shutdown");
    expect(env.core.capture_readiness(owner, page, env.peer.now) == 0 &&
           (page.records[0].ready.events & (ready_read | ready_eof | ready_read_closed | ready_write)) ==
            (ready_read | ready_eof | ready_read_closed | ready_write), "page records independent shutdown directions");
    expect(!(env.readiness(owner, handle).events & ready_read_closed), "legacy snapshot retains original bit mask");
    env.peer.tcp_packet(env.peer.tcp_connection(), ack_bit | psh_bit, incoming); env.poll();
    expect(env.receive(owner, handle).flags == eof && !env.readiness(owner, handle).readable_bytes,
           "late peer data is ACKed and discarded after read shutdown");
    const auto outgoing = pattern(49);
    expect(env.send(owner, handle, outgoing).result == static_cast<i64>(outgoing.size()), "write direction remains usable");
    env.poll();
    expect(env.peer.tcp_connection().client_data == outgoing, "real peer receives surviving write half");
    expect(env.request(owner, operation::shutdown_write, handle).result == 0, "both directions can shut independently");
    env.poll();
    expect(env.peer.tcp_fin_count == 1 && !env.peer.tcp_rst_count, "combined shutdown emits one clean FIN");
}
void read_shutdown_after_clean_fin() {
    // The two SHUT_RDWR wire operations can straddle a completed peer FIN.
    environment env; const u32 other = env.attach();
    const u64 ended = env.connected_tcp(other);
    const auto incoming = pattern(37);
    env.peer.answer_fin = false; env.peer.echo_tcp = false;
    auto& remote = env.peer.tcp_connection();
    env.peer.tcp_packet(remote, ack_bit | psh_bit, incoming); env.poll();
    expect(env.request(other, operation::shutdown_write, ended).result == 0, "write shutdown before read discard");
    env.poll();
    env.peer.tcp_packet(remote, ack_bit | fin_bit); env.poll();
    expect(env.request(other, operation::shutdown_read, ended).result == 0,
           "read shutdown succeeds after clean transport retirement");
    expect(env.receive(other, ended).flags == eof && !env.readiness(other, ended).readable_bytes,
           "retired transport buffered input is discarded without PCB access");
}
void tcp_level_readiness() {
    environment env; const u32 slot = env.attach(); env.peer.answer_syn = false;
    const u64 handle = env.open(slot, protocol::tcp); env.poll();
    auto pending = env.readiness(slot, handle);
    expect(pending.events == ready_connecting && !pending.readable_bytes && !pending.writable_bytes,
           "connecting is not writable");
    expect(env.request(slot, operation::shutdown_write, handle).result == would_block, "shutdown pending connect is not accepted");
    auto& remote = env.peer.tcp_connection(); remote.peer_next = 0x12987533;
    env.peer.tcp_packet(remote, syn_bit | ack_bit); env.poll();
    auto ready = env.readiness(slot, handle);
    expect(ready.events == ready_write && ready.writable_bytes && ready.generation > pending.generation,
           "established socket reports actual send capacity");
    expect(env.readiness(slot, handle).generation == ready.generation, "unchanged level has stable generation");
    const auto incoming = pattern(87); env.peer.tcp_packet(remote, ack_bit | psh_bit, incoming); env.poll();
    auto readable = env.readiness(slot, handle);
    expect((readable.events & ready_read) && readable.readable_bytes == incoming.size() &&
           readable.generation > ready.generation, "queued byte count reported without consuming");
    expect(env.receive(slot, handle, 12).length == 12, "partial readiness read");
    expect(env.readiness(slot, handle).readable_bytes == incoming.size() - 12, "readiness rechecks after consumption");
    env.peer.tcp_packet(remote, rst_bit | ack_bit); env.poll();
    auto reset_state = env.readiness(slot, handle);
    expect(reset_state.error == reset && (reset_state.events & (ready_read | ready_error)) == (ready_read | ready_error)
           && !reset_state.writable_bytes, "buffered input and reset reported together");
    expect(env.receive(slot, handle).length == incoming.size() - 12, "reset does not discard earlier bytes");
    expect(env.readiness(slot, handle).events == ready_error, "after draining reset only error is ready");
}
void tcp_readiness_backpressure() {
    environment env; const u32 slot = env.attach(); const u64 handle = env.connected_tcp(slot);
    env.peer.answer_data = false; env.peer.echo_tcp = false;
    for (;;) {
        const auto sent = env.send(slot, handle, pattern(payload_bytes)).result;
        if (sent == would_block) break;
        expect(sent > 0, "fill actual TCP send queue");
    }
    const auto blocked = env.readiness(slot, handle);
    expect(!(blocked.events & ready_write) && !blocked.writable_bytes, "connection state does not imply writable");
    env.peer.tcp_packet(env.peer.tcp_connection(), ack_bit); env.poll();
    expect(env.readiness(slot, handle).events & ready_write, "real ACK restores write readiness");
}
void tcp_half_close_keeps_receive() {
    environment env; const u32 slot = env.attach(); const u64 handle = env.connected_tcp(slot);
    env.peer.answer_fin = false; env.peer.echo_tcp = false;
    const auto outgoing = pattern(311), incoming = pattern(199, 71);
    env.peer.tcp_packet(env.peer.tcp_connection(), ack_bit | psh_bit, incoming); env.poll();
    expect(env.send(slot, handle, outgoing).result == static_cast<i64>(outgoing.size()), "send before half-close");
    expect(env.request(slot, operation::shutdown_write, handle).result == 0, "half-close accepts FIN with unread input");
    expect(env.core.connection_count() == 1, "half-close retains public handle");
    expect(env.request(slot, operation::shutdown_write, handle).result == 0, "repeat half-close idempotent");
    expect(env.send(slot, handle, bytes{1}).result == closed, "write after half-close rejected");
    env.poll();
    expect(env.peer.tcp_fin_count == 1 && !env.peer.tcp_rst_count && env.peer.tcp_connection().client_data == outgoing,
           "peer receives queued bytes followed by exactly one FIN");
    auto state = env.readiness(slot, handle);
    expect((state.events & (ready_read | ready_write_closed)) == (ready_read | ready_write_closed) &&
           !(state.events & (ready_write | ready_eof)), "receive remains open after local FIN");
    const auto received = env.receive(slot, handle);
    expect(bytes(received.data, received.data + received.length) == incoming, "half-close preserves unread input");
    const auto after_fin = pattern(43, 19);
    env.peer.tcp_packet(env.peer.tcp_connection(), ack_bit | psh_bit, after_fin); env.poll();
    expect(env.receive(slot, handle).length == after_fin.size(), "peer can send after observing local FIN");
    env.peer.tcp_packet(env.peer.tcp_connection(), ack_bit | fin_bit); env.poll();
    state = env.readiness(slot, handle);
    expect(state.events == (ready_read | ready_eof | ready_write_closed), "remote FIN is readable clean EOF");
    env.peer.now += 130'000'000'000ull; env.poll();
    expect(env.receive(slot, handle).flags == eof, "EOF survives TIME_WAIT PCB expiry without stale pointer");
    expect(env.request(slot, operation::close, handle).result == 0 && !env.core.connection_count(), "final close releases half-closed handle");
}
void tcp_half_close_passive_and_pressure() {
    environment env; const u32 slot = env.attach(); const u64 handle = env.connected_tcp(slot);
    env.peer.tcp_packet(env.peer.tcp_connection(), ack_bit | fin_bit); env.poll();
    std::vector<void*> segments;
    while (void* segment = memp_malloc(MEMP_TCP_SEG)) segments.push_back(segment);
    expect(env.request(slot, operation::shutdown_write, handle).result == 0, "FIN memory pressure accepted by pinned lwIP retry");
    expect(env.readiness(slot, handle).events == (ready_read | ready_eof | ready_write_closed), "pending FIN keeps EOF level");
    for (void* segment : segments) memp_free(MEMP_TCP_SEG, segment);
    env.peer.now += 250'000'000ull; env.poll(); env.poll();
    expect(env.receive(slot, handle).flags == eof, "LAST_ACK clean completion preserves EOF");
    expect(!env.readiness(slot, handle).error && env.peer.tcp_fin_count == 1, "clean completion is not an error");
    expect(env.request(slot, operation::close, handle).result == 0, "close completed passive half-close");
}
void tcp_echo_and_eof() {
    environment env; const u32 slot = env.attach(); const u64 handle = env.connected_tcp(slot);
    const auto payload = pattern(997);
    expect(env.send(slot, handle, payload).result == static_cast<i64>(payload.size()), "TCP send accepted exact bytes");
    env.poll(); bytes received;
    while (received.size() < payload.size()) {
        const auto reply = env.receive(slot, handle, 71);
        expect(reply.result == 0 && reply.length && reply.length <= 71 && !reply.flags, "TCP bounded short read");
        received.insert(received.end(), reply.data, reply.data + reply.length);
    }
    expect(received == payload, "TCP binary echo matches wire payload");
    expect(env.receive(slot, handle).result == would_block, "TCP empty receive is backpressure");
    env.peer.tcp_packet(env.peer.tcp_connection(), ack_bit | fin_bit); env.poll();
    const auto eof_reply = env.receive(slot, handle);
    expect(!eof_reply.result && !eof_reply.length && eof_reply.flags == eof, "peer FIN becomes clean EOF");
    expect(env.request(slot, operation::close, handle).result == 0, "TCP orderly close"); env.poll();
    expect(env.core.connection_count() == 0, "orderly close releases handle");
}
void tcp_short_write_pressure() {
    environment env; const u32 slot = env.attach(); const u64 handle = env.connected_tcp(slot);
    env.peer.answer_data = false; env.peer.echo_tcp = false;
    const auto payload = pattern(payload_bytes); u32 accepted = 0; bool short_write = false, blocked = false;
    for (u32 i = 0; i < 20; ++i) {
        const auto reply = env.send(slot, handle, payload);
        if (reply.result == would_block) { blocked = true; break; }
        expect(reply.result > 0 && reply.result <= payload_bytes, "TCP positive bounded admission");
        accepted += static_cast<u32>(reply.result); short_write |= reply.result < payload_bytes;
    }
    expect(short_write && blocked && accepted == TCP_SND_BUF, "real lwIP send buffer yields short write then backpressure");
    env.peer.answer_data = true; env.peer.tcp_packet(env.peer.tcp_connection(), ack_bit); env.poll();
    expect(env.send(slot, handle, bytes{1, 2, 3}).result == 3, "peer acknowledgements restore send capacity");
    expect(env.request(slot, operation::cancel, handle).result == 0, "cancel stalled connection");
}
void tcp_close_unread_preserves_data() {
    environment env; const u32 slot = env.attach(); const u64 handle = env.connected_tcp(slot);
    env.peer.echo_tcp = false;
    const auto incoming = pattern(517, 29), outgoing = pattern(383, 71);
    env.peer.tcp_packet(env.peer.tcp_connection(), ack_bit | psh_bit, incoming); env.poll();
    env.peer.transmit_blocked = true;
    expect(env.send(slot, handle, outgoing).result == static_cast<i64>(outgoing.size()),
           "queued TCP output is admitted before the blocked close");
    expect(env.request(slot, operation::close, handle).result == would_block,
           "unread TCP data defers orderly close and retains the handle");
    expect(env.core.connection_count() == 1 && !env.peer.tcp_fin_count && !env.peer.tcp_rst_count,
           "deferred close neither destroys ownership nor emits FIN/RST");
    const auto first = env.receive(slot, handle, 113);
    expect(first.result == 0 && first.length == 113 && !first.flags, "unread TCP bytes survive close retry");
    expect(env.request(slot, operation::close, handle).result == would_block,
           "partial receive still defers close");
    const auto last = env.receive(slot, handle);
    bytes received(first.data, first.data + first.length); received.insert(received.end(), last.data, last.data + last.length);
    expect(last.result == 0 && received == incoming, "all original unread bytes remain in order");
    env.peer.transmit_blocked = false;
    expect(env.request(slot, operation::close, handle).result == 0, "drained TCP receive permits orderly close");
    env.poll();
    expect(env.peer.tcp_fin_count == 1 && env.peer.tcp_rst_count == 0, "drained close emits FIN instead of RST");
    expect(env.peer.tcp_connection().client_data == outgoing, "all previously queued output reaches peer before FIN");
    expect(env.core.connection_count() == 0, "accepted orderly close releases application handle");
}
void tcp_close_fin_memory_pressure() {
    environment env; const u32 slot = env.attach(); const u64 handle = env.connected_tcp(slot);
    std::vector<void*> segments;
    while (void* segment = memp_malloc(MEMP_TCP_SEG)) segments.push_back(segment);
    expect(segments.size() == MEMP_NUM_TCP_SEG, "real TCP segment pool is fully exhausted after handshake");
    expect(env.request(slot, operation::close, handle).result == 0,
           "pinned lwIP accepts pending FIN and owns its timer retry");
    expect(!env.peer.tcp_fin_count && !env.peer.tcp_rst_count, "allocation pressure emits neither FIN nor reset");
    const u64 next = env.open(slot);
    expect(next > handle, "application slot can be reused while lwIP owns pending FIN");
    for (void* segment : segments) memp_free(MEMP_TCP_SEG, segment);
    env.peer.now += 250'000'000ull; env.poll(); env.poll();
    expect(env.peer.tcp_fin_count == 1 && !env.peer.tcp_rst_count, "timer sends FIN when segment memory returns");
    const auto payload = pattern(71, 12);
    expect(env.send(slot, next, payload).result == static_cast<i64>(payload.size()), "old FIN callbacks leave replacement UDP connection intact");
    env.poll(); const auto reply = env.receive(slot, next);
    expect(reply.result == 0 && bytes(reply.data, reply.data + reply.length) == payload,
           "replacement connection receives only its own data");
}
void tcp_close_reused_slot_callbacks() {
    environment env; const u32 slot = env.attach(); const u64 handle = env.connected_tcp(slot);
    env.peer.answer_data = false;
    expect(env.request(slot, operation::close, handle).result == 0, "start closing old TCP connection");
    const u64 next = env.open(slot);
    env.peer.tcp_packet(env.peer.tcp_connection(), rst_bit | ack_bit); env.poll();
    const auto status = env.request(slot, operation::status, next);
    expect(status.result == 0 && status.flags == connected, "late old TCP error cannot mutate reused UDP slot");
    expect(env.send(slot, next, bytes{1, 9, 2}).result == 3, "replacement connection stays usable after late reset");
}
void tcp_closing_pool_preserves_other_application() {
    environment env; const u32 victim = env.attach(), churn = env.attach(102);
    const u64 victim_handle = env.connected_tcp(victim);
    env.peer.answer_data = false; env.peer.echo_tcp = false;
    // One app keeps closing connections whose FIN is unacknowledged. Their
    // public handles are gone, but the real PCB pool still contains them.
    for (u32 i = 0; i < connection_limit - 1; ++i) {
        env.peer.now += 500'000'000ull; env.poll();
        const u64 handle = env.open(churn, protocol::tcp, static_cast<u16>(9100 + i));
        env.poll();
        expect(env.request(churn, operation::status, handle).flags == connected, "churn connection established");
        expect(env.request(churn, operation::close, handle).result == 0, "churn FIN accepted while peer withholds ACK");
    }
    auto request = env.input(churn, operation::open); request.address = permitted_address;
    request.port = 9200; request.transport = protocol::tcp;
    const auto reply = env.dispatch(churn, request);
    const auto survivor = env.request(victim, operation::status, victim_handle);
    expect(survivor.result == 0 && survivor.flags == connected,
           "one application's close churn must never make lwIP evict another application's live PCB");
    expect(reply.result == resources && !reply.object, "physical closing PCBs impose backpressure before lwIP eviction");
    expect(env.core.connection_count() == 1, "failed churn OPEN leaves other application ownership intact");
    env.core.shutdown(); env.stack.shutdown();
    std::vector<void*> pcbs;
    while (void* pcb = memp_malloc(MEMP_TCP_PCB)) pcbs.push_back(pcb);
    expect(pcbs.size() == MEMP_NUM_TCP_PCB,
           "stack shutdown reclaims the active PCB and all FIN-pending PCBs handed to lwIP");
    for (void* pcb : pcbs) memp_free(MEMP_TCP_PCB, pcb);
}
void tcp_receive_wrap_and_reset() {
    environment env; const u32 slot = env.attach(); const u64 handle = env.connected_tcp(slot);
    bytes expected, received; u32 split_writes = 0;
    for (u32 chunk = 0; chunk < 24; ++chunk) {
        const auto payload = pattern(997, chunk * 53);
        if (expected.size() % tcp_receive_bytes + payload.size() > tcp_receive_bytes) {
            ++split_writes;
            expect(received.size() < expected.size(), "split tail write occurs with earlier unread bytes in ring");
        }
        expected.insert(expected.end(), payload.begin(), payload.end());
        env.peer.tcp_packet(env.peer.tcp_connection(), ack_bit | psh_bit, payload); env.poll();
        // Keep a varying nonempty suffix while adding the next different
        // payload. Neither size divides 8192, exercising both copy fragments.
        while (expected.size() - received.size() > 613) {
            const auto reply = env.receive(slot, handle, 613);
            expect(reply.result == 0 && reply.length == 613, "TCP receive crosses ring boundary with queued suffix");
            received.insert(received.end(), reply.data, reply.data + reply.length);
        }
    }
    while (received.size() < expected.size()) {
        const auto reply = env.receive(slot, handle, 137);
        expect(reply.result == 0 && reply.length, "drain wrapped TCP receive suffix");
        received.insert(received.end(), reply.data, reply.data + reply.length);
    }
    expect(split_writes >= 2 && received == expected, "split writes and partial reads preserve every differently phased byte");
    const auto last = pattern(33); env.peer.tcp_packet(env.peer.tcp_connection(), ack_bit | psh_bit, last); env.poll();
    env.peer.tcp_packet(env.peer.tcp_connection(), rst_bit | ack_bit); env.poll();
    const auto status = env.request(slot, operation::status, handle);
    expect(status.result == reset && status.flags == failed, "peer RST terminates connection");
    const auto buffered = env.receive(slot, handle);
    expect(buffered.result == 0 && bytes(buffered.data, buffered.data + buffered.length) == last,
           "already received bytes remain readable before reset");
    expect(env.receive(slot, handle).result == reset, "reset surfaced after buffered bytes");
    expect(env.request(slot, operation::cancel, handle).result == 0, "reset PCB ownership cleans up once");
}
void tcp_connect_deadline() {
    environment env; const u32 slot = env.attach(); env.peer.answer_syn = false;
    const u64 handle = env.open(slot, protocol::tcp); env.poll();
    env.peer.now += 5'000'000'000ull - 1; env.poll();
    expect(env.request(slot, operation::status, handle).flags == connecting, "TCP deadline not early");
    ++env.peer.now; env.poll(); const auto reply = env.request(slot, operation::status, handle);
    expect(reply.result == timeout && reply.flags == failed, "TCP connect deadline aborts real PCB");
    expect(env.request(slot, operation::cancel, handle).result == 0, "timed-out handle can be released");
    expect(env.core.connection_count() == 0, "deadline cleanup accounts resources");
}
void tcp_late_handshake() {
    environment env; const u32 slot = env.attach(); env.peer.answer_syn = false;
    const u64 handle = env.open(slot, protocol::tcp); env.poll();
    auto& connection = env.peer.tcp_connection(); connection.peer_next = 0x12345678;
    env.peer.tcp_packet(connection, syn_bit | ack_bit);
    env.peer.now += 5'000'000'000ull; env.poll();
    const auto reply = env.request(slot, operation::status, handle);
    expect(reply.result == timeout && reply.flags == failed,
           "SYN-ACK processed after the open deadline cannot establish a connection");
}
void tcp_handshake_callback_deadline() {
    environment env; const u32 slot = env.attach(); env.peer.answer_syn = false;
    const u64 handle = env.open(slot, protocol::tcp); env.poll();
    auto& connection = env.peer.tcp_connection(); connection.peer_next = 0x12345678;
    env.peer.tcp_packet(connection, syn_bit | ack_bit);
    // The initial poll time is valid; processing the queued frame crosses the
    // deadline and exercises tcp_abort/ERR_ABRT inside the connected callback.
    env.peer.received_frame_advance = 5'000'000'000ull; env.poll();
    const auto reply = env.request(slot, operation::status, handle);
    expect(reply.result == timeout && reply.flags == failed, "callback rechecks its absolute deadline");
    expect(env.request(slot, operation::cancel, handle).result == 0, "aborted callback does not retain a freed PCB");
}
void tcp_timer_retransmission() {
    environment env; const u32 slot = env.attach(); env.peer.answer_syn = false;
    auto input = env.input(slot, operation::open); input.transport = protocol::tcp;
    input.address = permitted_address; input.port = 9000; input.deadline = env.peer.now + max_request_ns;
    const auto opened = env.dispatch(slot, input); expect(!opened.result, "open timer probe"); env.poll();
    for (u32 i = 0; i < 20; ++i) { env.peer.now += 250'000'000ull; env.poll(); }
    expect(env.peer.tcp_syn_count >= 2, "sys_check_timeouts drives real SYN retransmission");
    expect(env.request(slot, operation::status, opened.object).flags == connecting, "retransmission respects original connect deadline");
}
void udp_binary_and_empty() {
    environment env; const u32 slot = env.attach(); const u64 handle = env.open(slot);
    for (const auto& payload : {pattern(payload_bytes), bytes{}, bytes{0, 255, 0, 1}}) {
        expect(env.send(slot, handle, payload).result == static_cast<i64>(payload.size()), "UDP datagram admitted");
        env.poll(); const auto reply = env.receive(slot, handle);
        expect(reply.result == 0 && bytes(reply.data, reply.data + reply.length) == payload && !reply.flags,
               "UDP preserves binary and empty datagrams");
        expect(env.receive(slot, handle).result == would_block, "one receive consumes exactly one UDP datagram");
    }
    expect(env.request(slot, operation::close, handle).result == 0, "UDP close releases PCB");
}
void udp_pressure_and_source_filter() {
    environment env; const u32 slot = env.attach(); const u64 handle = env.open(slot);
    env.peer.echo_udp = false; expect(env.send(slot, handle, bytes{1}).result == 1, "discover UDP endpoint"); env.poll();
    env.peer.udp_packet(bytes{9}, 9001); env.poll();
    expect(env.receive(slot, handle).result == would_block, "connected UDP filters foreign source port");
    env.peer.udp_packet(pattern(payload_bytes + 1)); env.poll();
    expect(env.receive(slot, handle).result == would_block, "oversize UDP datagram is rejected while queue is empty");
    auto info_reply = env.request(slot, operation::information); information info{};
    std::memcpy(&info, info_reply.data, sizeof(info)); expect(info.udp_dropped == 1, "oversize alone increments drop count");
    const std::array<bytes, 4> accepted{pattern(3), bytes{}, pattern(123), pattern(payload_bytes)};
    for (const auto& payload : accepted) env.peer.udp_packet(payload);
    env.peer.udp_packet(pattern(7)); env.poll();
    const auto small = env.receive(slot, handle, 1);
    expect(small.result == buffer_too_small && small.flags == 3 && !small.length, "too-small UDP receive retains full datagram");
    for (const auto& payload : accepted) {
        const auto reply = env.receive(slot, handle);
        expect(reply.result == 0 && bytes(reply.data, reply.data + reply.length) == payload, "UDP queue preserves accepted datagram order");
    }
    expect(env.receive(slot, handle).result == would_block, "full UDP queue drops new data");
    info_reply = env.request(slot, operation::information);
    std::memcpy(&info, info_reply.data, sizeof(info)); expect(info.udp_dropped == 2, "UDP pressure and oversize drops are counted");
}
void link_backpressure_and_budget() {
    environment env; const u32 slot = env.attach(); const u64 handle = env.open(slot);
    env.peer.echo_udp = false; expect(env.send(slot, handle, bytes{1}).result == 1, "prime ARP"); env.poll();
    const auto before = env.peer.output.size(); env.peer.transmit_blocked = true;
    expect(env.send(slot, handle, bytes{2, 3}).result == would_block, "link queue pressure maps to backpressure");
    expect(env.peer.output.size() == before, "blocked frame was not delivered");
    env.peer.transmit_blocked = false;
    expect(env.send(slot, handle, bytes{2, 3}).result == 2, "explicit retry after non-admission succeeds");
    for (u32 i = 0; i < 100; ++i) env.peer.input.push_back(env.peer.ethernet(0x1234, 46));
    env.poll(); expect(env.peer.input.size() == 36, "one poll processes at most 64 frames");
    env.poll(); expect(env.peer.input.empty(), "next poll makes bounded progress");
}
void transport_faults() {
    environment env; env.peer.input.push_back(bytes(1515));
    expect(env.stack.poll() == io, "oversized device result fails closed");
    expect(env.stack.poll() == io, "transport failure remains latched");
}
void clock_failure() {
    environment env; env.peer.clock_failed = true;
    expect(env.stack.poll() == io, "negative monotonic clock stops stack");
}
void entropy_failure() {
    packet_peer peer; peer.random_failed = true; lwip_stack stack;
    expect(stack.initialize(peer.callbacks(), local_mac.data()) == io, "missing entropy rejects initialization");
    stack.shutdown();
}
void runtime_entropy_stops_transmit() {
    environment env;
    const u32 slot = env.attach();
    const u64 handle = env.open(slot);
    expect(env.send(slot, handle, bytes{1}).result == 1, "prime actual UDP/ARP path");
    env.poll();
    const auto frames = env.peer.output.size();
    env.peer.random_failed = true;
    u32 word = 0x12345678;
    expect(env.stack.random_checked(word) == io && word == 0x12345678,
           "failed entropy read preserves output and latches transport fault");
    expect(env.send(slot, handle, bytes{2}).result == io,
           "existing UDP send observes latched entropy failure");
    expect(env.peer.output.size() == frames, "fatal entropy state cannot emit frames");
    env.peer.random_failed = false;
    expect(env.stack.random_checked(word) == io && env.stack.poll() == io,
           "later successful entropy cannot silently recover the failed stack");
    env.core.shutdown(); env.stack.shutdown();
    std::vector<void*> pcbs;
    while (void* pcb = memp_malloc(MEMP_UDP_PCB)) pcbs.push_back(pcb);
    expect(pcbs.size() == MEMP_NUM_UDP_PCB, "shutdown returns all UDP PCBs after entropy failure");
    for (void* pcb : pcbs) memp_free(MEMP_UDP_PCB, pcb);
}
struct test_case { const char* name; void (*run)(); };
const test_case cases[] = {
    {"admission_and_stop", admission_and_stop}, {"framing_and_replay", framing_and_replay},
    {"address_policy", address_policy}, {"object_isolation", object_isolation},
    {"trusted_egress_policy", trusted_egress_policy}, {"invalid_egress_fails_closed", invalid_egress_fails_closed},
    {"connection_quotas", connection_quotas}, {"revoke_policy", revoke_policy},
    {"deadlines_and_idle", deadlines_and_idle}, {"tcp_echo_and_eof", tcp_echo_and_eof},
    {"socket_capabilities_and_isolation", socket_capabilities_and_isolation},
    {"readiness_page_and_read_shutdown", readiness_page_and_read_shutdown},
    {"read_shutdown_after_clean_fin", read_shutdown_after_clean_fin},
    {"tcp_level_readiness", tcp_level_readiness}, {"tcp_readiness_backpressure", tcp_readiness_backpressure},
    {"tcp_half_close_keeps_receive", tcp_half_close_keeps_receive},
    {"tcp_half_close_passive_and_pressure", tcp_half_close_passive_and_pressure},
    {"tcp_short_write_pressure", tcp_short_write_pressure}, {"tcp_receive_wrap_and_reset", tcp_receive_wrap_and_reset},
    {"tcp_close_unread_preserves_data", tcp_close_unread_preserves_data},
    {"tcp_close_fin_memory_pressure", tcp_close_fin_memory_pressure},
    {"tcp_close_reused_slot_callbacks", tcp_close_reused_slot_callbacks},
    {"tcp_closing_pool_preserves_other_application", tcp_closing_pool_preserves_other_application},
    {"tcp_connect_deadline", tcp_connect_deadline}, {"tcp_late_handshake", tcp_late_handshake},
    {"tcp_handshake_callback_deadline", tcp_handshake_callback_deadline},
    {"tcp_timer_retransmission", tcp_timer_retransmission},
    {"udp_binary_and_empty", udp_binary_and_empty}, {"udp_pressure_and_source_filter", udp_pressure_and_source_filter},
    {"link_backpressure_and_budget", link_backpressure_and_budget}, {"transport_faults", transport_faults},
    {"clock_failure", clock_failure}, {"entropy_failure", entropy_failure},
    {"runtime_entropy_stops_transmit", runtime_entropy_stops_transmit}};
}
int main(int argc, char** argv) {
    if (argc == 2 && std::strcmp(argv[1], "--list") == 0) {
        for (const auto& item : cases) std::puts(item.name);
        return 0;
    }
    if (argc != 2) return 2;
    for (const auto& item : cases) if (std::strcmp(argv[1], item.name) == 0) {
        item.run(); std::printf("NET_SERVICE_CASE_PASS=%s\n", item.name); return 0;
    }
    return 2;
}
