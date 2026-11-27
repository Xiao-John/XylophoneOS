// SPDX-License-Identifier: Apache-2.0
#ifndef XOS_TEST_GLIBC_INET_ADDRESSES_H
#define XOS_TEST_GLIBC_INET_ADDRESSES_H

#include <netinet/in.h>
#include <stddef.h>
#include <string.h>

#ifdef __cplusplus
# define CHECK_LAYOUT static_assert
#else
# define CHECK_LAYOUT _Static_assert
#endif

CHECK_LAYOUT(sizeof(sa_family_t) == 2, "address family width");
CHECK_LAYOUT(sizeof(struct sockaddr) == 16 && offsetof(struct sockaddr, sa_family) == 0,
             "generic socket address layout");
CHECK_LAYOUT(sizeof(struct sockaddr_storage) == 128, "socket address storage size");
CHECK_LAYOUT(sizeof(in_addr_t) == 4 && sizeof(in_port_t) == 2, "address and port widths");
CHECK_LAYOUT(sizeof(struct in_addr) == 4 && sizeof(struct in6_addr) == 16, "IP address widths");
CHECK_LAYOUT(sizeof(struct sockaddr_in) == 16 && offsetof(struct sockaddr_in, sin_family) == 0
             && offsetof(struct sockaddr_in, sin_port) == 2 && offsetof(struct sockaddr_in, sin_addr) == 4,
             "IPv4 socket address layout");
CHECK_LAYOUT(sizeof(struct sockaddr_in6) == 28 && offsetof(struct sockaddr_in6, sin6_family) == 0
             && offsetof(struct sockaddr_in6, sin6_port) == 2 && offsetof(struct sockaddr_in6, sin6_flowinfo) == 4
             && offsetof(struct sockaddr_in6, sin6_addr) == 8 && offsetof(struct sockaddr_in6, sin6_scope_id) == 24,
             "IPv6 socket address layout");

#undef CHECK_LAYOUT

static int check_addresses(void)
{
    // Taking and calling volatile function pointers also verifies the actual libc symbols.
    uint32_t (*volatile host_to_net32)(uint32_t) = htonl;
    uint32_t (*volatile net_to_host32)(uint32_t) = ntohl;
    uint16_t (*volatile host_to_net16)(uint16_t) = htons;
    uint16_t (*volatile net_to_host16)(uint16_t) = ntohs;
    const unsigned char ipv4_bytes[] = { 10, 0, 2, 2 };
    const unsigned char port_bytes[] = { 0x12, 0x34 };
    const unsigned char loopback_bytes[] = { 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1 };
    const struct in6_addr any = IN6ADDR_ANY_INIT;
    const struct in6_addr loopback = IN6ADDR_LOOPBACK_INIT;
    struct sockaddr_in ipv4;
    memset(&ipv4, 0, sizeof(ipv4));
    ipv4.sin_family = AF_INET;
    ipv4.sin_port = host_to_net16(0x1234);
    ipv4.sin_addr.s_addr = host_to_net32(0x0a000202);
    struct sockaddr_in6 ipv6;
    memset(&ipv6, 0, sizeof(ipv6));
    ipv6.sin6_family = AF_INET6;
    ipv6.sin6_port = ipv4.sin_port;
    ipv6.sin6_addr = in6addr_loopback;
    return !memcmp(&ipv4.sin_addr.s_addr, ipv4_bytes, sizeof(ipv4_bytes))
        && !memcmp(&ipv4.sin_port, port_bytes, sizeof(port_bytes))
        && net_to_host32(ipv4.sin_addr.s_addr) == 0x0a000202
        && net_to_host16(ipv6.sin6_port) == 0x1234
        && htonl(0x0a000202) == ipv4.sin_addr.s_addr && htons(0x1234) == ipv4.sin_port
        && !memcmp(ipv6.sin6_addr.s6_addr, loopback_bytes, sizeof(loopback_bytes))
        && !memcmp(&in6addr_any, &any, sizeof(any)) && !memcmp(&in6addr_loopback, &loopback, sizeof(loopback))
        && IN6_IS_ADDR_UNSPECIFIED(&in6addr_any) && IN6_IS_ADDR_LOOPBACK(&in6addr_loopback);
}

#endif
