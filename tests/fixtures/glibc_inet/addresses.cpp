// SPDX-License-Identifier: Apache-2.0
#include <sys/socket.h>
#include "addresses.h"
#include <stdio.h>
#include <xos/net_service_abi.hpp>

static_assert(__is_standard_layout(sockaddr_in));
static_assert(__is_standard_layout(sockaddr_in6));
static_assert(offsetof(xos::net2::message, address) == 40);
static_assert(offsetof(xos::net2::message, port) == 44);

int main()
{
    if (!check_addresses())
        return 1;
    const sockaddr_in address{ AF_INET, htons(0x1234), { htonl(0x0a000202) }, {} };
    xos::net2::message open{};
    open.address = ntohl(address.sin_addr.s_addr);
    open.port = ntohs(address.sin_port);
    // Net2 v2 stores scalar fields in little-endian order after the conversion.
    const unsigned char wire_address[] = { 2, 2, 0, 10 };
    const unsigned char wire_port[] = { 0x34, 0x12 };
    if (open.address != xos::net2::permitted_address || open.port != 0x1234
        || memcmp(&open.address, wire_address, sizeof(wire_address))
        || memcmp(&open.port, wire_port, sizeof(wire_port)))
        return 2;
    puts("GLIBC_INET_CXX_PASS layout bytes symbols ipv6 net2");
    return 0;
}
