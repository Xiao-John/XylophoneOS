// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "http.hpp"
#include "../native_tls/stream.hpp"

namespace browser_http {
// The caller chooses the authenticated service, expected route and trusted DER anchor.
// In net2_dns mode the resolver's result must still equal the expected address.
struct https_route {
    xos::u64 service_pid;
    xos::u32 address;
    const unsigned char* trust_anchor;
    size_t trust_anchor_size;
    native_tls::route_source source;
};

// Fetch one HTTPS response before the absolute deadline. The result describes
// the verified wire bytes in buffer, including the header and body spans.
xos::i64 fetch_https(const https_route& route, const url& target, unsigned char* buffer,
                     size_t capacity, xos::u64 deadline, response& result);
}
