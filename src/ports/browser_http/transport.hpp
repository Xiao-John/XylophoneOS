// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "http.hpp"
#include <xos/net_transport.hpp>

namespace browser_http {
// The reader returns zero on verified end of stream, or a negative transport error.
using response_reader = xos::i64 (*)(void*, unsigned char*, xos::u32);
xos::i64 read_framed_response(response_reader read, void* context,
                              unsigned char* buffer, size_t capacity, response& result);

// Return at the exact, fully parsed Content-Length boundary. This does not
// authenticate stream termination: the TLS caller must finish its shutdown,
// require the peer close_notify, and reject pending application data before
// accepting or exposing the response. The EOF-checking entry above is unchanged.
xos::i64 read_content_length_response(response_reader read, void* context,
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
