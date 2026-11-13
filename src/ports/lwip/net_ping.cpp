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
raw_pcb* g_icmp;
u16 g_identifier = 0x584f;
u16 g_sequence;
u16 g_expected;
volatile bool g_replied;
u32 g_sent_at_ms;

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

u16_t icmp_checksum(const u8* data, u16 length) {
    u32 sum = 0;
    for (u16 i = 0; i + 1 < length; i += 2) {
        sum += static_cast<u32>((data[i] << 8) | data[i + 1]);
    }
    if ((length & 1) != 0) { sum += static_cast<u32>(data[length - 1] << 8); }
    while ((sum >> 16) != 0) { sum = (sum & 0xffffu) + (sum >> 16); }
    return static_cast<u16>(~sum);
}

u8_t on_icmp(void*, raw_pcb*, pbuf* packet, const ip_addr_t*) {
    if (packet->len < sizeof(ip_hdr) + sizeof(icmp_echo_hdr)) { pbuf_free(packet); return 1; }
    // lwIP's raw API delivers the IPv4 header; skip it to reach ICMP.
    const auto* iph = static_cast<const ip_hdr*>(packet->payload);
    const u16_t header_length = IPH_HL_BYTES(iph);
    if (packet->len < header_length + sizeof(icmp_echo_hdr)) { pbuf_free(packet); return 1; }
    const auto* header = reinterpret_cast<const icmp_echo_hdr*>(
        static_cast<const u8*>(packet->payload) + header_length);
    if (header->type == ICMP_ER && header->id == htons(g_identifier)
        && header->seqno == htons(g_expected)) {
        g_replied = true;
    }
    pbuf_free(packet);
    return 1;
}

void send_ping(u16 sequence) {
    constexpr u16 payload = 32;
    pbuf* packet = pbuf_alloc(PBUF_IP, sizeof(icmp_echo_hdr) + payload, PBUF_RAM);
    if (packet == nullptr) { return; }
    auto* header = static_cast<icmp_echo_hdr*>(packet->payload);
    header->type = ICMP_ECHO;
    header->code = 0;
    header->chksum = 0;
    header->id = htons(g_identifier);
    header->seqno = htons(sequence);
    u8* body = static_cast<u8*>(packet->payload) + sizeof(icmp_echo_hdr);
    for (u16 i = 0; i < payload; ++i) { body[i] = static_cast<u8>(sequence + i); }
    header->chksum = htons(icmp_checksum(static_cast<const u8*>(packet->payload),
                                         sizeof(icmp_echo_hdr) + payload));
    ip_addr_t gateway;
    IP_ADDR4(&gateway, 10, 0, 2, 2);
    g_expected = sequence;
    g_replied = false;
    g_sent_at_ms = sys_now();
    (void)raw_sendto(g_icmp, packet, &gateway);
    pbuf_free(packet);
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
    g_icmp = raw_new(IP_PROTO_ICMP);
    if (g_icmp == nullptr) { return false; }
    raw_recv(g_icmp, on_icmp, nullptr);
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

extern "C" int net_ping_main(void) {
    if (!bring_up()) {
        xos::sdk::print("[net_ping] service_unavailable\n");
        return 2;
    }
    printf("[net_ping] mac=%02x:%02x:%02x:%02x:%02x:%02x ip=10.0.2.15 gateway=10.0.2.2\n",
           g_mac[0], g_mac[1], g_mac[2], g_mac[3], g_mac[4], g_mac[5]);

    for (u16 sequence = 1; sequence <= 8; ++sequence) {
        send_ping(sequence);
        const u32 deadline = g_sent_at_ms + 400;
        while (static_cast<i32>(deadline - sys_now()) > 0) {
            poll_frames();
            sys_check_timeouts();
            if (g_replied) {
                printf("[net_ping] reply seq=%u rtt_ms=%u\n",
                       static_cast<unsigned>(sequence),
                       static_cast<unsigned>(sys_now() - g_sent_at_ms));
                g_client.close();
                return 0;
            }
            xos::sdk::syscall(xos::sys_sleep_until, now_ns() + 2'000'000ull);
        }
    }
    xos::sdk::print("[net_ping] icmp_timeout\n");
    g_client.close();
    return 1;
}

int main() { return net_ping_main(); }
