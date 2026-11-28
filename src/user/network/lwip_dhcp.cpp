// SPDX-License-Identifier: Apache-2.0
#include "lwip_stack.hpp"
#ifdef XOS_LWIP_DHCP_AUTHORITY
extern "C" {
#include "lwip/dhcp.h"
#include "lwip/acd.h"
#include "lwip/etharp.h"
#include "lwip/prot/dhcp.h"
err_t dhcp_xos_rebind(struct netif*);
}
namespace {
using namespace xos;
u16 read16(const u8* p) { return (static_cast<u16>(p[0]) << 8) | p[1]; }
u32 read32(const u8* p) { return (static_cast<u32>(read16(p)) << 16) | read16(p + 2); }
struct dhcp* client_of(netif* interface) { return netif_dhcp_data(interface); }
void increment(u32& count) { if (count != ~u32{0}) ++count; }
bool phase_of(u8 state, xos::user::network::dhcp::phase& result) {
    using xos::user::network::dhcp::phase;
    switch (state) {
    case DHCP_STATE_SELECTING: result = phase::selecting; return true;
    case DHCP_STATE_REQUESTING: result = phase::requesting; return true;
    case DHCP_STATE_RENEWING: result = phase::renewing; return true;
    case DHCP_STATE_REBINDING: result = phase::rebinding; return true;
    default: return false;
    }
}
}
extern "C" int xos_lwip_dhcp_reply(netif* interface, pbuf* packet, const ip_addr_t* source, u16_t port) {
    return static_cast<xos::user::network::lwip_stack*>(interface->state)->dhcp_reply(packet, source, port);
}
extern "C" int xos_lwip_dhcp_bind(netif* interface) {
    return static_cast<xos::user::network::lwip_stack*>(interface->state)->dhcp_bind();
}
extern "C" int xos_lwip_dhcp_acd(netif* interface, int state) {
    return static_cast<xos::user::network::lwip_stack*>(interface->state)->dhcp_acd(state);
}
namespace xos::user::network {
bool lwip_stack::restart_clock(u64 now, bool new_budget) {
    if (new_budget) {
        if (now > ~u64{0} - acquisition_budget_) return false;
        acquisition_deadline_ = now + acquisition_budget_;
    }
    return acquisition_deadline_ > now &&
        lease_.start(now, acquisition_deadline_) == dhcp::error::none;
}
i64 lwip_stack::start_dhcp(const dhcp::policy& policy, u64 budget,
                           configuration_publisher publisher, void* context) {
    if (!active_ || dhcp_enabled_ || !publisher || !budget || budget > dhcp::acquisition_limit_ns ||
        dhcp::validate_policy(policy) != dhcp::error::none) return net2::invalid;
    const auto clock = monotonic_time();
    if (clock < 0) return net2::io;
    dhcp_policy_ = policy; acquisition_budget_ = budget; publish_ = publisher; publisher_ = context;
    if (!restart_clock(static_cast<u64>(clock), true)) return net2::invalid;
    dhcp_enabled_ = true;
    return start_dhcp_client(static_cast<u64>(clock));
}
void lwip_stack::stop_dhcp_client() {
    start_retry_at_ = 0;
    dhcp_release_and_stop(&interface_);
    // If the shared DHCP UDP PCB allocation failed, upstream returns with its
    // client OFF but its ACD node already linked. OFF's stop is a no-op, so
    // detach that node explicitly before reuse or freeing the client.
    auto* client = client_of(&interface_);
    if (client) for (auto* item = interface_.acd_list; item; item = item->next) {
        if (item == &client->acd) { acd_remove(&interface_, item); break; }
    }
    etharp_cleanup_netif(&interface_);
}
i64 lwip_stack::start_dhcp_client(u64 now) {
    start_retry_at_ = 0;
    increment(start_attempts_);
    const auto result = dhcp_start(&interface_);
    if (result == ERR_OK) return failure_;
    increment(start_failures_);
    stop_dhcp_client();
    if (failure_) return failure_;
    if (result != ERR_MEM) { failure_ = net2::io; return failure_; }
    // dhcp_start cannot run after client/UDP PCB allocation failure. Retry
    // only from the outer loop, twice per second within the original deadline.
    // DISCOVER frame pressure uses upstream fine-timer retransmission.
    if (now < acquisition_deadline_) {
        const u64 remaining = acquisition_deadline_ - now;
        start_retry_at_ = now + (remaining < 500'000'000ull ? remaining : 500'000'000ull);
    }
    return 0;
}
void lwip_stack::retire_dhcp() {
    gate_open_ = false;
    // Block output before aborting TCP (which can emit RST) and before dropping
    // ARP's deferred IP packets. No old application packet can cross the gate.
    etharp_cleanup_netif(&interface_);
    for (u32 slot = 0; slot < net2::connection_limit; ++slot) (void)close(slot, true);
    configure_dns(0);
    if (published_ && !publish_(publisher_, 0, 0, 0, 0)) failure_ = net2::io;
    published_ = false;
    netif_set_addr(&interface_, IP4_ADDR_ANY4, IP4_ADDR_ANY4, IP4_ADDR_ANY4);
    retire_pending_ = false;
}
void lwip_stack::observe_dhcp(u64 now) {
    if (!dhcp_enabled_) return;
    const auto event = lease_.advance(now);
    if (event.next == dhcp::action::renew) renew_pending_ = true;
    if (event.next == dhcp::action::rebind) { renew_pending_ = false; rebind_pending_ = true; }
    if (event.next == dhcp::action::expire || event.next == dhcp::action::acquisition_failed ||
        event.next == dhcp::action::clock_failed) {
        last_reason_ = lease_.last_reason(); gate_open_ = false;
        retire_pending_ = true; stop_pending_ = true;
        renew_pending_ = rebind_pending_ = false;
        // A previously usable lease may begin a new bounded acquisition. An
        // exhausted acquisition or unapproved candidate cannot renew its budget.
        restart_pending_ = event.next == dhcp::action::expire && event.revoke;
        if (restart_pending_) acquisition_deadline_ = 0;
        if (event.next == dhcp::action::clock_failed) failure_ = net2::io;
    }
}
i64 lwip_stack::advance_dhcp() {
    if (!dhcp_enabled_) return failure_;
    const auto clock = monotonic_time();
    if (clock < 0) {
        (void)lease_.invalidate(dhcp::reason::clock_failure);
        last_reason_ = dhcp::reason::clock_failure;
        gate_open_ = false; retire_dhcp(); return net2::io;
    }
    const auto now = static_cast<u64>(clock);
    observe_dhcp(now);
    if (retire_pending_) retire_dhcp();
    if (stop_pending_) {
        stop_pending_ = false;
        // Executed outside UDP, ARP and TCP callbacks: never free an active PCB.
        stop_dhcp_client();
    }
    if (restart_pending_) {
        restart_pending_ = false;
        if (restart_clock(now, !acquisition_deadline_)) (void)start_dhcp_client(now);
    }
    if (start_retry_at_ && now >= start_retry_at_ && !failure_) (void)start_dhcp_client(now);
    auto* client = client_of(&interface_);
    if (client && (renew_pending_ || rebind_pending_)) {
        const bool rebind = rebind_pending_;
        renew_pending_ = rebind_pending_ = false;
        if (client->state == DHCP_STATE_BOUND) {
            u32 xid = 0;
            if (dhcp_xid(xid)) return failure_;
            client->xid = xid;
        }
        const auto result = rebind ? dhcp_xos_rebind(&interface_) : dhcp_renew(&interface_);
        if (result != ERR_OK && result != ERR_MEM && result != ERR_RTE) failure_ = net2::io;
    }
    return failure_;
}
int lwip_stack::dhcp_xid(u32& output) {
    for (u32 attempt = 0; attempt < 4; ++attempt) {
        u32 word = 0;
        if (random_checked(word)) return ERR_IF;
        if (word && word != last_xid_) { output = last_xid_ = word; return ERR_OK; }
    }
    failure_ = net2::io;
    return ERR_IF;
}
int lwip_stack::dhcp_reply(pbuf* packet, const ip_addr_t* source, u16_t port) {
    const auto clock = monotonic_time();
    if (clock < 0) return ERR_IF;
    const auto now = static_cast<u64>(clock);
    observe_dhcp(now);
    auto* client = client_of(&interface_);
    dhcp::reply_context expected{};
    if (!dhcp_enabled_ || stop_pending_ || !client || !packet || !source ||
        packet->tot_len > dhcp::reply_limit || !phase_of(client->state, expected.state)) {
        increment(rejected_); return ERR_VAL;
    }
    expected.xid = client->xid;
    for (u32 i = 0; i < 6; ++i) expected.mac[i] = interface_.hwaddr[i];
    // Backoff retains lwIP's last offered server. SELECTING has no issuer yet.
    if (expected.state != dhcp::phase::selecting) {
        expected.selected_server = lwip_ntohl(ip4_addr_get_u32(ip_2_ip4(&client->server_ip_addr)));
        expected.requested_address = lwip_ntohl(ip4_addr_get_u32(&client->offered_ip_addr));
    }
    u8 bytes[dhcp::reply_limit];
    if (pbuf_copy_partial(packet, bytes, packet->tot_len, 0) != packet->tot_len) return ERR_VAL;
    dhcp::reply reply{};
    if (dhcp::validate_reply(bytes, packet->tot_len, lwip_ntohl(ip4_addr_get_u32(ip_2_ip4(source))),
                             port, expected, dhcp_policy_, reply) != dhcp::error::none || reply.resolver_count > 1) {
        increment(rejected_); return ERR_VAL;
    }
    if (reply.type == dhcp::message_type::ack) {
        dhcp::candidate_result candidate{};
        if (lease_.accept_ack(reply, now, candidate) != dhcp::error::none) {
            increment(rejected_); return ERR_VAL;
        }
        candidate_generation_ = candidate.generation;
    } else if (reply.type == dhcp::message_type::nak) {
        bool revoke = false;
        if (lease_.accept_nak(reply, now, revoke) != dhcp::error::none) {
            increment(rejected_); return ERR_VAL;
        }
        last_reason_ = dhcp::reason::nak; gate_open_ = false;
        retire_pending_ = stop_pending_ = restart_pending_ = true;
        renew_pending_ = rebind_pending_ = false;
        if (revoke) acquisition_deadline_ = 0;
        increment(accepted_);
        // Outer poll performs stop/start; upstream must not mutate or restart
        // from inside its receive callback or grant another acquisition budget.
        return ERR_VAL;
    }
    increment(accepted_);
    return ERR_OK;
}
int lwip_stack::dhcp_bind() {
    const auto clock = monotonic_time();
    if (clock < 0) return ERR_IF;
    const auto now = static_cast<u64>(clock);
    observe_dhcp(now);
    bool changed = false;
    if (stop_pending_ || lease_.approve_address(candidate_generation_, now, changed) != dhcp::error::none)
        return ERR_VAL;
    if (changed) {
        gate_open_ = false;
        etharp_cleanup_netif(&interface_);
        for (u32 slot = 0; slot < net2::connection_limit; ++slot) (void)close(slot, true);
        const auto& value = lease_.current().configuration;
        if (!publish_(publisher_, value.address, value.mask, value.gateway,
                      value.resolver_count ? value.resolvers[0] : 0)) {
            (void)lease_.invalidate(dhcp::reason::stopped); failure_ = net2::io; return ERR_IF;
        }
    }
    published_ = gate_open_ = true;
    acquisition_deadline_ = 0;
    return ERR_OK;
}
int lwip_stack::dhcp_acd(int state) {
    const auto clock = monotonic_time();
    if (clock < 0) return ERR_IF;
    const auto now = static_cast<u64>(clock);
    observe_dhcp(now);
    if (stop_pending_) return ERR_VAL;
    if (state == ACD_DECLINE) {
        const bool revoke = lease_.invalidate(dhcp::reason::conflict);
        last_reason_ = dhcp::reason::conflict;
        increment(conflicts_); gate_open_ = false; retire_pending_ = true;
        renew_pending_ = rebind_pending_ = false;
        if (!restart_clock(now, revoke)) { stop_pending_ = true; return ERR_VAL; }
    }
    return ERR_OK;
}
bool lwip_stack::dhcp_wire(const u8* frame, u32 length, u64 now, bool committed) {
    // This boundary sees actual Ethernet transmission, including ARP-deferred
    // REQUESTs. Queuing an unresolved UDP datagram never starts a lease clock.
    if (!dhcp_enabled_) return false;
    if (!committed) observe_dhcp(now);
    if (length < 14) return false;
    const u16 ether_type = read16(frame + 12);
    if (ether_type == 0x0806) return !stop_pending_ &&
        (lease_.usable(now) || (acquisition_deadline_ && now < acquisition_deadline_));
    if (ether_type != 0x0800 || length < 34) return false;
    const u32 ihl = (frame[14] & 15u) * 4;
    if (ihl < 20 || length < 14 + ihl || (frame[14] >> 4) != 4) return false;
    const u8* ip = frame + 14;
    if (ip[9] == 17 && length >= 14 + ihl + 8 && read16(ip + ihl) == 68 && read16(ip + ihl + 2) == 67) {
        const u8* bytes = ip + ihl + 8;
        const u32 size = length - 14 - ihl - 8;
        auto* client = client_of(&interface_);
        if (size < 241 || !client || stop_pending_ || read32(bytes + 4) != client->xid ||
            read32(bytes + 236) != 0x63825363) return false;
        u8 type = 0;
        for (u32 offset = 240; offset < size;) {
            const u8 code = bytes[offset++];
            if (code == 255) break;
            if (!code) continue;
            if (offset >= size || bytes[offset] > size - offset - 1) return false;
            const u8 count = bytes[offset++];
            if (code == 53 && count == 1) type = bytes[offset];
            offset += count;
        }
        if (type == 1 || type == 4) return acquisition_deadline_ && now < acquisition_deadline_;
        if (type != 3) return false;
        dhcp::phase phase{};
        if (!phase_of(client->state, phase) || phase == dhcp::phase::selecting) return false;
        if (committed) return lease_.note_request_sent(phase, client->xid, now) == dhcp::error::none;
        auto trial = lease_;
        return trial.note_request_sent(phase, client->xid, now) == dhcp::error::none;
    }
    return gate_open_ && lease_.usable(now) && read32(ip + 12) == lease_.current().configuration.address;
}
i64 lwip_stack::lease_status(net2::lease_snapshot& output) {
    if (!dhcp_enabled_) return net2::unsupported;
    if (advance_dhcp()) return net2::io;
    const auto clock = monotonic_time();
    if (clock < 0) return net2::io;
    observe_dhcp(static_cast<u64>(clock));
    if (retire_pending_) retire_dhcp();
    output = {};
    output.revision = net2::lease_revision;
    output.state = static_cast<u32>(lease_.current_state());
    output.reason = static_cast<u32>(last_reason_);
    output.accepted = accepted_; output.rejected = rejected_; output.conflicts = conflicts_;
    output.start_attempts = start_attempts_; output.start_failures = start_failures_;
    if (lease_.usable(static_cast<u64>(clock))) {
        const auto& value = lease_.current();
        output.request_sent = value.request_sent; output.t1 = value.t1;
        output.t2 = value.t2; output.expires = value.expires;
        output.server = value.configuration.server; output.address = value.configuration.address;
        output.mask = value.configuration.mask; output.gateway = value.configuration.gateway;
        output.resolver = value.configuration.resolver_count ? value.configuration.resolvers[0] : 0;
    }
    return 0;
}
}
#endif
