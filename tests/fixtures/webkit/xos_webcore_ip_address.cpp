// SPDX-License-Identifier: Apache-2.0
#include "config.h"
#include "DNS.h"

#include <cstdio>
#include <wtf/MainThread.h>
#include <wtf/URL.h>
#include <wtf/text/WTFString.h>

int main()
{
    using WebCore::IPAddress;
    using WebCore::isIPAddressDisallowed;

    WTF::initializeMainThread();
    const auto loopback4 = IPAddress::fromString("127.0.0.1"_s);
    const auto loopback6 = IPAddress::fromString("[::1]"_s);
    if (!loopback4 || !loopback4->isIPv4() || !loopback4->isLoopback()
        || !loopback6 || !loopback6->isIPv6() || !loopback6->isLoopback())
        return 1;

    const auto ipv4 = IPAddress::fromString("192.0.2.1"_s);
    const auto ipv4Next = IPAddress::fromString("192.0.2.0"_s);
    const auto ipv6 = IPAddress::fromString("2001:db8::a"_s);
    const auto ipv6Next = IPAddress::fromString("2001:db8::b"_s);
    if (!ipv4 || !ipv4Next || !ipv6 || !ipv6Next
        || ipv4->matchingNetMaskLength(*ipv4Next) != 31
        || ipv6->matchingNetMaskLength(*ipv6Next) != 127
        || ipv4->matchingNetMaskLength(*ipv6) != 0
        || ipv6->isolatedCopy() != *ipv6)
        return 2;

    const URL zero4 { "http://0.0.0.0/"_s };
    const URL zero6 { "http://[::]/"_s };
    const URL documentAddress { "http://[2001:db8::a]/"_s };
    if (!zero4.isValid() || !zero6.isValid() || !documentAddress.isValid()
        || !isIPAddressDisallowed(zero4) || !isIPAddressDisallowed(zero6)
        || isIPAddressDisallowed(documentAddress))
        return 3;
    if (IPAddress::fromString("127.0.0.01"_s) || IPAddress::fromString("[192.0.2.1]"_s)
        || IPAddress::fromString("[:::]"_s) || IPAddress::fromString("fe80::1%net"_s))
        return 4;

    std::puts("XOS_WEBCORE_IP_POLICY_OK");
    return 0;
}
