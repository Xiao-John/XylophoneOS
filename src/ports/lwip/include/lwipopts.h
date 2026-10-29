// SPDX-License-Identifier: Apache-2.0
#pragma once
// Frozen experimental userspace raw API profile. No socket/netconn compatibility.
#define NO_SYS 1
// One service event loop; lwIP never called from a device ISR.
#define SYS_LIGHTWEIGHT_PROT 0
#define LWIP_SOCKET 0
#define LWIP_NETCONN 0
#define LWIP_IPV4 1
#define LWIP_IPV6 0
#define LWIP_ARP 1
#define LWIP_ETHERNET 1
#define LWIP_ICMP 1
#define LWIP_UDP 1
#define LWIP_TCP 1
#define LWIP_DHCP 1
#define LWIP_DNS 1
#define LWIP_RAW 1
#define LWIP_STATS 1
#define MEM_SIZE (128 * 1024)
#define MEM_ALIGNMENT 8
#define PBUF_POOL_SIZE 32
#define PBUF_POOL_BUFSIZE 1536
#define MEMP_NUM_PBUF 32
#define MEMP_NUM_UDP_PCB 8
#define MEMP_NUM_TCP_PCB 8
#define MEMP_NUM_TCP_PCB_LISTEN 4
#define MEMP_NUM_TCP_SEG 32
#define TCP_MSS 1460
#define TCP_WND (4 * TCP_MSS)
#define TCP_SND_BUF (4 * TCP_MSS)
#define TCP_SND_QUEUELEN 16
#define IP_REASSEMBLY 0
#define IP_FRAG 0
#define LWIP_NETIF_HOSTNAME 0
#define LWIP_DNS_SECURE 7
#define LWIP_DHCP_DOES_ACD_CHECK 0
#define LWIP_AUTOIP 0
#define LWIP_IGMP 0
#define LWIP_TIMERS 1
