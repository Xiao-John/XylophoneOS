// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "service_core.hpp"
#include "dhcp_policy.hpp"
extern "C" {
#include "lwip/netif.h"
#include "lwip/tcp.h"
#include "lwip/udp.h"
}

namespace xos::user::network {
struct frame_io {
    void* context;
    i64 (*receive)(void*, u8*, u32);
    i64 (*transmit)(void*, const u8*, u32);
    i64 (*clock)(void*);
    i64 (*random)(void*, u32&);
};
class lwip_stack {
public:
    i64 initialize(const frame_io& io, const u8* mac);
    void shutdown();
    i64 poll();
    stack_api api();
    resolver_api dns_api();
    i64 monotonic_time();
    u32 milliseconds();
    u32 random_word();
    i64 random_checked(u32& result);
    void fault() { failure_ = net2::io; }
#ifdef XOS_LWIP_DHCP_AUTHORITY
    using configuration_publisher = bool (*)(void*, u32, u32, u32, u32);
    i64 start_dhcp(const dhcp::policy&, u64 budget, configuration_publisher, void*);
    i64 advance_dhcp();
    i64 lease_status(net2::lease_snapshot&);
    int dhcp_reply(pbuf*, const ip_addr_t*, u16_t);
    int dhcp_bind();
    int dhcp_acd(int state);
    int dhcp_xid(u32&);
#endif
private:
    struct connection {
        tcp_pcb* tcp;
        udp_pcb* udp;
        u64 deadline;
        i64 error;
        bool established, ended, write_closed;
        net2::readiness_snapshot ready;
        u32 head, count;
        u16 datagram_lengths[net2::udp_queue_limit];
        u8 data[net2::tcp_receive_bytes];
    } connections_[net2::connection_limit]{};
    frame_io io_{};
    netif interface_{};
    i64 failure_ = 0;
    u32 dropped_ = 0;
    bool active_ = false;
#ifdef XOS_LWIP_DHCP_AUTHORITY
    dhcp::policy dhcp_policy_{};
    dhcp::lease_clock lease_{};
    configuration_publisher publish_ = nullptr;
    void* publisher_ = nullptr;
    u64 acquisition_budget_ = 0, acquisition_deadline_ = 0, candidate_generation_ = 0;
    u32 last_xid_ = 0, accepted_ = 0, rejected_ = 0, conflicts_ = 0;
    dhcp::reason last_reason_ = dhcp::reason::none;
    bool dhcp_enabled_ = false, published_ = false, gate_open_ = false;
    bool stop_pending_ = false, restart_pending_ = false, renew_pending_ = false, rebind_pending_ = false;
    bool retire_pending_ = false;
    void observe_dhcp(u64 now);
    void retire_dhcp();
    bool restart_clock(u64 now, bool new_budget);
    bool dhcp_wire(const u8*, u32, u64, bool committed);
#endif
#ifdef XOS_LWIP_DNS_LIFETIME
    struct dns_subscription { u64 token; resolver_completion callback; void* owner; } subscriptions_[net2::client_sessions]{};
    void configure_dns(u32 address);
    i64 resolve_name(const char* name, u64 token, resolver_completion callback, void* owner);
    void cancel_dns(u64 token);
    static void on_dns_found(const char*, const ip_addr_t*, void*);
#endif
    i64 open(u32 slot, net2::protocol transport, u32 address, u16 port, u64 deadline);
    i64 status(u32 slot, u32& flags);
    i64 send(u32 slot, const u8* data, u32 length);
    i64 receive(u32 slot, u8* data, u32 capacity, u32& length, u32& flags);
    i64 close(u32 slot, bool aborting);
    i64 readiness(u32 slot, net2::readiness_snapshot& snapshot);
    i64 shutdown_write(u32 slot);
    void expire_connects(u64 now);
    static err_t link_output(netif*, pbuf*);
    static err_t configure(netif*);
    static err_t on_connected(void*, tcp_pcb*, err_t);
    static void on_error(void*, err_t);
    static err_t on_receive(void*, tcp_pcb*, pbuf*, err_t);
    static void on_datagram(void*, udp_pcb*, pbuf*, const ip_addr_t*, u16_t);
};
}
