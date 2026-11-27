// SPDX-License-Identifier: Apache-2.0
#include "XOSIPAddress.h"

#include <cstdio>

using WebCore::XOSIPAddress::IPv4;
using WebCore::XOSIPAddress::IPv6;
using WebCore::XOSIPAddress::parseIPv4;
using WebCore::XOSIPAddress::parseIPv6;

int main()
{
    if (parseIPv4("0.0.0.0") != IPv4 { }
        || parseIPv4("127.0.0.1") != IPv4 { 127, 0, 0, 1 }
        || parseIPv4("192.0.2.255") != IPv4 { 192, 0, 2, 255 }
        || parseIPv4("255.255.255.255") != IPv4 { 255, 255, 255, 255 })
        return 1;
    for (auto input : { "", "0.0.0", "127.0.0.1.", "127.0.0.01", "256.0.0.1", "1..2.3.4", "0x7f.0.0.1", " 127.0.0.1" }) {
        if (parseIPv4(input))
            return 2;
    }

    if (parseIPv6("::") != IPv6 { }
        || parseIPv6("::1") != IPv6 { 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1 }
        || parseIPv6("2001:DB8:1234::") != IPv6 { 0x20, 0x01, 0x0d, 0xb8, 0x12, 0x34 }
        || parseIPv6("2001:DB8::1:2") != IPv6 { 0x20, 0x01, 0x0d, 0xb8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 2 }
        || parseIPv6("::ffff:192.0.2.1") != IPv6 { 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 255, 255, 192, 0, 2, 1 }
        || parseIPv6("1:2:3:4:5:6:7:8") != IPv6 { 0, 1, 0, 2, 0, 3, 0, 4, 0, 5, 0, 6, 0, 7, 0, 8 })
        return 3;
    for (auto input : { "", ":", ":::", "1::2::3", "1:2:3:4:5:6:7::8", "1:2:3:4:5:6:7:8:",
             "1:2:3:4:5:6:7", "::10.0.0.1:7", "::ffff:01.0.0.1", "::ffff:256.0.0.1", "10000::", "fe80::1%eth0" }) {
        if (parseIPv6(input))
            return 4;
    }

    if (parseIPv4(std::string_view { "127.0.0.1\0x", 11 })
        || parseIPv6(std::string_view { "::1\0x", 5 }))
        return 5;
    std::puts("XOS_WEBCORE_IP_ADDRESS_OK");
    return 0;
}
