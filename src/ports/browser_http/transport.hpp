// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "http.hpp"
#include <xos/net_transport.hpp>

namespace browser_http {
// The reader returns zero on verified end of stream, or a negative transport error.
using response_reader = xos::i64 (*)(void*, unsigned char*, xos::u32);
// The caller supplies at least max_headers bytes of workspace. All status codes
// reach the sink: callers must check result.status and discard provisional
// output on error, including truncated or unauthenticated EOF.
using response_sink = xos::i64 (*)(void*, const unsigned char*, xos::u32);
xos::i64 read_streamed_response(response_reader read, void* read_context,
                                 response_sink sink, void* sink_context,
                                 unsigned char* header_buffer, size_t header_capacity,
                                 size_t body_limit, response& result);
xos::i64 read_framed_response(response_reader read, void* context,
                              unsigned char* buffer, size_t capacity, response& result);

// Caller provides a connected PID-pinned native client and a total absolute
// monotonic deadline. The buffer contains exact HTTP wire bytes; response
// body_offset/body_length select the fully framed body. Numeric IPv4 only.
// Redirects stay on the original address and port. max_redirects=0 returns the
// first response without following it; other values are limited to five.
xos::i64 fetch(xos::net2::client& client, const url& input, unsigned char* buffer,
               size_t capacity, xos::u64 deadline, response& result, url& final_url,
               unsigned max_redirects = 5);
}
