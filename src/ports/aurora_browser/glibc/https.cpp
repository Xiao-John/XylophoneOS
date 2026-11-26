// SPDX-License-Identifier: Apache-2.0
#include "../../browser_http/https_transport.hpp"
#include "clarke_https_origin.hpp"
#include "tls_test_root.h"
#include <string.h>

namespace browser {
xos::i64 fetch_https(xos::u64 service, const browser_http::url& target,
                    unsigned char* bytes, size_t capacity, xos::u64 deadline,
                    browser_http::response& response) {
    using namespace xos;
    if (target.protocol != browser_http::scheme::https || target.port != clarke_tls_port ||
        strcmp(target.host, clarke_tls_host) != 0) return net2::denied;
    u32 address = 0;
    if (!net2::parse_ipv4(clarke_tls_address, address)) return net2::invalid;
    const auto route = clarke_tls_resolve_net2 ? native_tls::route_source::net2_dns : native_tls::route_source::pinned;
    return browser_http::fetch_https({service, address, tls_test_root, sizeof tls_test_root, route},
                                     target, bytes, capacity, deadline, response);
}
}
