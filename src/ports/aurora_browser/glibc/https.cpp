// SPDX-License-Identifier: Apache-2.0
#include "../../browser_http/transport.hpp"
#include "../../native_tls/stream.hpp"
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
    char request[browser_http::max_url + 512];
    size_t length = 0;
    if (browser_http::get_request(target, request, sizeof(request), length) != browser_http::error::ok)
        return net2::invalid;

    native_tls::stream stream;
    const auto route = clarke_tls_resolve_net2 ? native_tls::route_source::net2_dns : native_tls::route_source::pinned;
    const auto connected = stream.connect(service, address, target.port, target.host,
                                          tls_test_root, sizeof(tls_test_root), deadline, route);
    if (connected) return connected;
    for (size_t sent = 0; sent < length;) {
        const int count = stream.write(reinterpret_cast<const unsigned char*>(request) + sent, length - sent);
        if (count <= 0) return count ? count : net2::io;
        sent += static_cast<size_t>(count);
    }
    browser_http::response parsed{};
    const auto result = browser_http::read_framed_response(
        [](void* state, unsigned char* buffer, u32 size) -> i64 {
            return static_cast<native_tls::stream*>(state)->read(buffer, size);
        }, &stream, bytes, capacity, parsed);
    if (result) return result;
    const int finished = stream.finish();
    if (finished) return finished;
    response = parsed;
    return 0;
}
}
