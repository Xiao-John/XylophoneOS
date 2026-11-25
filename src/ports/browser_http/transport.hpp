// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "http.hpp"
#include <xos/net_transport.hpp>

namespace browser_http {
// Caller provides a connected PID-pinned native client and a total absolute
// monotonic deadline. The buffer contains exact HTTP wire bytes; response
// body_offset/body_length select the fully framed body. Numeric IPv4 only.
// Redirects stay on the original address and port. max_redirects=0 returns the
// first response without following it; other values are limited to five.
xos::i64 fetch(xos::net2::client& client, const url& input, unsigned char* buffer,
               size_t capacity, xos::u64 deadline, response& result, url& final_url,
               unsigned max_redirects = 5);
}
