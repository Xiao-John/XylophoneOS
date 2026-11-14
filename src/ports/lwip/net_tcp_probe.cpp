/* SPDX-License-Identifier: Apache-2.0 */
/* lwIP raw-API smoke test over the XOS raw-frame net service. */
#include <stdio.h>
#include <xos/net_client.hpp>
#include <xos/sdk.hpp>

extern "C" {
#include "lwip/init.h"
#include "lwip/ip4_addr.h"
#include "lwip/icmp.h"
#include "lwip/ip.h"
#include "lwip/netif.h"
#include "lwip/pbuf.h"
#include "lwip/raw.h"
#include "lwip/tcp.h"
#include <stdlib.h>
#include <string.h>
#include "lwip/sys.h"
#include "lwip/timeouts.h"
#include "lwip/inet_chksum.h"
#include "lwip/etharp.h"
#include "netif/ethernet.h"
}

#include "xos_lwip.h"

namespace {
using xos::u8;
using xos::u16;
using xos::u32;
using xos::u64;
using xos::i32;
using xos::i64;
xos::net::client g_client;
u8 g_mac[6]{};
struct netif g_netif;
tcp_pcb* g_tcp;
bool g_connected, g_closed, g_failed;
u8 g_reply[64];
u16 g_reply_length;

u64 now_ns() { return static_cast<u64>(xos::sdk::syscall(xos::sys_clock_monotonic, 0)); }

i64 net_request(xos::net::operation action, const u8* data, u32 length,
                xos::net::message& reply, u64 timeout_ns) {
    return g_client.request(action, data, length, reply, now_ns() + timeout_ns);
}

void poll_frames() {
    for (unsigned i = 0; i < 4; ++i) {
        xos::net::message reply{};
        const i64 result = net_request(xos::net::operation::receive, nullptr, 0, reply, 25'000'000);
        if (result != 0 || reply.length == 0) { return; }
        pbuf* packet = pbuf_alloc(PBUF_RAW, static_cast<u16_t>(reply.length), PBUF_POOL);
        if (packet == nullptr) { return; }
        pbuf_take(packet, reply.data, static_cast<u16_t>(reply.length));
        if (g_netif.input(packet, &g_netif) != ERR_OK) { pbuf_free(packet); }
    }
}

err_t link_output(netif* netif, pbuf* packet) {
    (void)netif;
    u8 frame[1514];
    const u16_t size = pbuf_copy_partial(packet, frame, sizeof(frame), 0);
    if (size == 0 || size > sizeof(frame)) { return ERR_BUF; }
    xos::net::message reply{};
    const i64 result = net_request(xos::net::operation::transmit, frame, size, reply, 50'000'000);
    return result == 0 ? ERR_OK : ERR_IF;
}

err_t netif_init(netif* netif) {
    netif->name[0] = 'x';
    netif->name[1] = 'n';
    netif->num = 0;
    netif->mtu = 1500;
    netif->hwaddr_len = 6;
    for (u32 i = 0; i < 6; ++i) { netif->hwaddr[i] = g_mac[i]; }
    netif->flags = NETIF_FLAG_BROADCAST | NETIF_FLAG_ETHARP | NETIF_FLAG_LINK_UP;
    netif->output = etharp_output;
    netif->linkoutput = link_output;
    return ERR_OK;
}

bool bring_up() {
    for (unsigned attempt = 0; attempt < 20; ++attempt) {
        if (g_client.connect() == 0) { break; }
        xos::sdk::syscall(xos::sys_sleep_until, now_ns() + 50'000'000ull);
    }
    xos::net::message info{};
    if (net_request(xos::net::operation::information, nullptr, 0, info, 100'000'000) != 0
        || info.length != 6) {
        return false;
    }
    for (u32 i = 0; i < 6; ++i) { g_mac[i] = info.data[i]; }

    lwip_init();
    ip4_addr_t address, mask, gateway;
    IP4_ADDR(&address, 10, 0, 2, 15);
    IP4_ADDR(&mask, 255, 255, 255, 0);
    IP4_ADDR(&gateway, 10, 0, 2, 2);
    if (netif_add(&g_netif, &address, &mask, &gateway, nullptr, netif_init, ethernet_input) == nullptr) {
        return false;
    }
    netif_set_default(&g_netif);
    netif_set_up(&g_netif);
    return true;
}
}  // namespace

extern "C" u32_t sys_now(void) {
    return static_cast<u32_t>(now_ns() / 1000000ull);
}

extern "C" uint32_t xos_lwip_rand(void) {
    return static_cast<uint32_t>(now_ns() ^ (now_ns() >> 17));
}

extern "C" void xos_lwip_diag(const char* format, ...) {
    char line[160];
    va_list args;
    va_start(args, format);
    const int length = vsnprintf(line, sizeof(line), format, args);
    va_end(args);
    if (length > 0) {
        xos::sdk::print(line);
        xos::sdk::print("\n");
    }
}

err_t on_connect(void*, tcp_pcb*, err_t error) { g_connected = error == ERR_OK; g_failed = error != ERR_OK; return error; }
void on_error(void*, err_t) { g_tcp = nullptr; g_failed = true; }
err_t on_receive(void*, tcp_pcb* pcb, pbuf* packet, err_t error) {
    if (error != ERR_OK) { if (packet) pbuf_free(packet); g_failed=true; return error; }
    if (!packet) { g_closed=true; return ERR_OK; }
    if (packet->tot_len > sizeof(g_reply)-g_reply_length) { pbuf_free(packet); g_failed=true; return ERR_OK; }
    const u16 length=packet->tot_len;
    pbuf_copy_partial(packet,g_reply+g_reply_length,length,0); g_reply_length+=length;
    tcp_recved(pcb,length); pbuf_free(packet); return ERR_OK;
}
int main(int argc, char** argv) {
    if (argc != 2) return 2;
    const long port=strtol(argv[1],nullptr,10); if (port<1 || port>65535 || !bring_up()) return 2;
    ip_addr_t host; IP_ADDR4(&host,10,0,2,2);
    g_tcp=tcp_new(); if (!g_tcp) return 3;
    tcp_err(g_tcp,on_error); tcp_recv(g_tcp,on_receive);
    if (tcp_connect(g_tcp,&host,static_cast<u16>(port),on_connect)!=ERR_OK) return 4;
    const u32 deadline=sys_now()+15000; bool sent=false;
    while (static_cast<i32>(deadline-sys_now())>0 && !g_failed) {
        poll_frames(); sys_check_timeouts();
        if (g_connected && !sent) {
            constexpr char request[]="XOS-TCP-PROBE-v1\n";
            if (tcp_write(g_tcp,request,sizeof(request)-1,TCP_WRITE_FLAG_COPY)!=ERR_OK || tcp_output(g_tcp)!=ERR_OK) { g_failed=true; break; }
            sent=true;
        }
        if (g_closed) {
            if (g_reply_length != 32 || !g_tcp) break;
            printf("TCP_REPLY:"); for (u16 i=0;i<g_reply_length;i++) printf("%02x",g_reply[i]); printf("\n");
            tcp_recv(g_tcp,nullptr); tcp_err(g_tcp,nullptr);
            if (tcp_close(g_tcp)!=ERR_OK) { tcp_abort(g_tcp); g_client.close(); return 5; }
            g_tcp=nullptr; g_client.close(); puts("TCP_GUEST_PASS"); return 0;
        }
        xos::sdk::syscall(xos::sys_sleep_until,now_ns()+2'000'000ull);
    }
    if (g_tcp) { tcp_err(g_tcp,nullptr); tcp_abort(g_tcp); } g_client.close();
    puts("TCP_GUEST_FAIL"); return 1;
}
