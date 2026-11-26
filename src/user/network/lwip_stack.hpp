// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "service_core.hpp"
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
private:
    struct connection {
        tcp_pcb* tcp;
        udp_pcb* udp;
        u64 deadline;
        i64 error;
        bool established, ended;
        u32 head, count;
        u16 datagram_lengths[net2::udp_queue_limit];
        u8 data[net2::tcp_receive_bytes];
    } connections_[net2::connection_limit]{};
    frame_io io_{};
    netif interface_{};
    i64 failure_ = 0;
    u32 dropped_ = 0;
    bool active_ = false;
#ifdef XOS_LWIP_DNS_LIFETIME
    struct dns_subscription { u64 token; resolver_completion callback; void* owner; } subscriptions_[net2::client_sessions]{};
    void configure_dns(bool enabled);
    i64 resolve_name(const char* name, u64 token, resolver_completion callback, void* owner);
    void cancel_dns(u64 token);
    static void on_dns_found(const char*, const ip_addr_t*, void*);
#endif
    i64 open(u32 slot, net2::protocol transport, u32 address, u16 port, u64 deadline);
    i64 status(u32 slot, u32& flags);
    i64 send(u32 slot, const u8* data, u32 length);
    i64 receive(u32 slot, u8* data, u32 capacity, u32& length, u32& flags);
    i64 close(u32 slot, bool aborting);
    void expire_connects(u64 now);
    static err_t link_output(netif*, pbuf*);
    static err_t configure(netif*);
    static err_t on_connected(void*, tcp_pcb*, err_t);
    static void on_error(void*, err_t);
    static err_t on_receive(void*, tcp_pcb*, pbuf*, err_t);
    static void on_datagram(void*, udp_pcb*, pbuf*, const ip_addr_t*, u16_t);
};
}
