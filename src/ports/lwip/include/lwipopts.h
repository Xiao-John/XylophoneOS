/* SPDX-License-Identifier: Apache-2.0 */
/* lwIP configuration for the XOS raw-frame net service (NO_SYS). */
#ifndef XOS_LWIPOPTS_H
#define XOS_LWIPOPTS_H

#define NO_SYS 1
#define SYS_LIGHTWEIGHT_PROT 0
#define LWIP_TIMERS 1

#define LWIP_IPV4 1
#define LWIP_IPV6 0
#define LWIP_ARP 1
#define LWIP_ETHERNET 1
#define LWIP_ICMP 1
#define LWIP_RAW 1
#define LWIP_UDP 1
#define LWIP_TCP 1

#define LWIP_DHCP 0
#define LWIP_AUTOIP 0
#define LWIP_IGMP 0
#define LWIP_DNS 0
#define LWIP_SOCKET 0
#define LWIP_NETCONN 0
#define LWIP_COMPAT_SOCKETS 0
#define LWIP_NETIF_HOSTNAME 1
#define LWIP_NETIF_STATUS_CALLBACK 0
#define LWIP_NETIF_LINK_CALLBACK 0

#define MEM_LIBC_MALLOC 0
#define MEM_SIZE (32 * 1024)
#define MEMP_NUM_PBUF 32
#define PBUF_POOL_SIZE 24
#define PBUF_POOL_BUFSIZE 1600
#define MEMP_NUM_ARP_QUEUE 8
#define MEMP_NUM_TCP_PCB 8
#define MEMP_NUM_TCP_SEG 32
#define TCP_MSS 1460
#define TCP_SND_BUF (4 * TCP_MSS)
#define TCP_WND (4 * TCP_MSS)
#define TCP_QUEUE_OOSEQ 0

#define LWIP_CHKSUM_ALGORITHM 3
#define CHECKSUM_GEN_IP 1
#define CHECKSUM_GEN_UDP 1
#define CHECKSUM_GEN_TCP 1
#define CHECKSUM_GEN_ICMP 1
#define CHECKSUM_CHECK_IP 1
#define CHECKSUM_CHECK_UDP 1
#define CHECKSUM_CHECK_TCP 1
#define CHECKSUM_CHECK_ICMP 1

#define LWIP_RAND() xos_lwip_rand()
#define LWIP_PLATFORM_DIAG(x) do { xos_lwip_diag x; } while (0)
#define LWIP_PLATFORM_ASSERT(x) do { xos_lwip_diag("lwip assert: %s", x); for (;;) {} } while (0)

#endif
