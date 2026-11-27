// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>

namespace xos::user::network::dhcp {
inline constexpr u32 reply_limit = 576, authority_limit = 2;
inline constexpr u64 second_ns = 1'000'000'000ull;
inline constexpr u64 acquisition_limit_ns = 60 * second_ns;

// All IPv4 values use numeric network notation: 10.0.2.2 == 0x0a000202,
// independent of the host's byte order. This is a direct Ethernet profile:
// no relays, option overload/concatenation, classless routes or infinite leases.
struct policy {
    u32 subnet, mask, first_address, last_address;
    u32 servers[authority_limit], server_count;
    u32 gateways[authority_limit], gateway_count;
    u32 resolvers[authority_limit], resolver_count;
    u32 max_lease_seconds;
};
enum class phase : u8 { selecting, requesting, renewing, rebinding };
enum class message_type : u8 { offer = 2, ack = 5, nak = 6 };
enum class error : u8 {
    none, argument, header, identity, options, authority, state,
    timing, overflow, expired, clock_regressed
};
struct reply_context {
    phase state;
    u32 xid;
    u8 mac[6];
    u32 selected_server;
    // Zero only while selecting. ACK must match the requested/current address.
    u32 requested_address;
};
struct reply {
    message_type type;
    u32 xid, server, address, mask, gateway;
    u32 resolvers[authority_limit], resolver_count;
    u32 lease_seconds, t1_seconds, t2_seconds;
    bool has_t1, has_t2;
};
error validate_policy(const policy& authority);
// On every failure, output remains byte-for-byte unchanged. The caller must
// validate the UDP/IP framing/checksum and copy a chained pbuf before this call.
error validate_reply(const u8* bytes, u32 length, u32 source_address,
                     u16 source_port, const reply_context& expected,
                     const policy& authority, reply& output);

struct lease {
    reply configuration;
    u64 request_sent, t1, t2, expires;
};
enum class state : u8 {
    disabled, selecting, requesting, checking, bound, renewing, rebinding,
    expired, failed
};
enum class reason : u8 {
    none, nak, conflict, link_lost, stopped, expiry, acquisition_timeout,
    clock_failure
};
enum class action : u8 { none, renew, rebind, expire, acquisition_failed, clock_failed };
struct event { action next; bool revoke; };
struct candidate_result {
    u64 generation;
    bool needs_acd, configuration_changed;
};

// Lease authorization only. lwIP still owns DHCP packets, retransmissions and
// RFC5227 ACD. Call advance() before every RX/application TX, before accepting
// replies, and before lwIP timers. Handle revoke before any application traffic.
class lease_clock {
public:
    // Only disabled/failed/expired clients may begin. No hidden infinite retry.
    error start(u64 now, u64 acquisition_deadline);
    // Only after a REQUEST actually left link_output successfully. The first
    // send for this xid wins, including retransmits and renewing -> rebinding.
    // After a successful lease, the next renewal must use a fresh random xid.
    error note_request_sent(phase request_phase, u32 xid, u64 now);
    // Accepts a parser-validated ACK into a candidate; never publishes it.
    error accept_ack(const reply& ack, u64 now, candidate_result& output);
    // A parser-validated NAK must also match an actually transmitted request.
    // On success, revoke says whether the old published epoch must be retired.
    error accept_nak(const reply& nak, u64 now, bool& revoke);
    // Only after ACD reports clear, or an unchanged address already passed ACD.
    // The generation prevents a stale callback approving a subsequent lease.
    error approve_address(u64 generation, u64 now, bool& configuration_changed);
    event advance(u64 now);
    // Return true when the adapter must revoke the previously published epoch.
    // NAK/conflict/link loss cancel requests and ACD candidates as well.
    bool invalidate(reason cause);
    bool usable(u64 now) const;
    bool has_candidate() const { return pending_; }
    const lease& current() const { return current_; }
    const lease& candidate() const { return candidate_; }
    state current_state() const { return state_; }
    reason last_reason() const { return reason_; }
private:
    lease current_{}, candidate_{};
    state state_ = state::disabled;
    reason reason_ = reason::none;
    u64 acquisition_deadline_ = 0, request_sent_ = 0, last_now_ = 0;
    u64 generation_ = 0;
    u32 request_xid_ = 0, last_bound_xid_ = 0;
    bool request_recorded_ = false, published_ = false, pending_ = false;
    bool bound_xid_recorded_ = false;
};
}
