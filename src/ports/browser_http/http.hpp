// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stddef.h>
#include <stdint.h>

// Pure, allocation-free parsing. No socket, TLS, DNS or privilege.
// The separate native transport enforces deadlines and controlled peers.
namespace browser_http {
constexpr size_t max_url = 2048, max_headers = 16384, max_body = 1024 * 1024;
enum class error { ok, need_more, invalid, unsupported, too_large, truncated };
enum class scheme { http, https };
constexpr uint16_t default_port(scheme protocol) { return protocol == scheme::https ? 443 : 80; }
struct url {
    char host[254]{};
    char target[max_url + 1]{};
    uint16_t port = 80;
    scheme protocol = scheme::http;
};
struct response {
    unsigned status = 0;
    // Wire header fields after the status line, excluding the final blank line.
    size_t headers_offset = 0, headers_length = 0;
    size_t body_offset = 0, body_length = 0;
    // A bounded Location copy; relative references are resolved separately.
    char location[max_url + 1]{};
};
error parse_url(const char* text, size_t size, url& out);
error resolve(const url& base, const char* reference, size_t size, url& out);
error get_request(const url& input, char* out, size_t capacity, size_t& size);
// GET responses only. Caller accumulates at most max_headers+max_body bytes.
// Content-Length framing only; transfer/content encodings are explicitly refused.
// EOF before declared completion is an error. Extra/pipelined bytes are refused.
error parse_response(const unsigned char* data, size_t size, bool eof, response& out);
bool is_redirect(unsigned status);
// At most five redirects; caller persists count and must enforce total deadline.
error redirect(const url& base, const response& value, unsigned& count, url& out);
const char* error_name(error value);
}
