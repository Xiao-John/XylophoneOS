// SPDX-License-Identifier: Apache-2.0
#include "transport.hpp"

namespace browser_http {
namespace {
xos::i64 parser_error(error value) {
    if (value == error::unsupported) return xos::net2::unsupported;
    if (value == error::too_large) return xos::net2::resources;
    if (value == error::truncated) return xos::net2::io;
    return xos::net2::invalid;
}
xos::i64 abandon(xos::net2::client& client, xos::u64 handle, xos::u64 deadline, xos::i64 result) {
    if (client.cancel_connection(handle, deadline)) client.close();
    return result;
}
xos::i64 read_response(response_reader read, void* context,
                       unsigned char* buffer, size_t capacity, response& result, bool require_eof) {
    using namespace xos;
    result = {};
    if (!read || !buffer || !capacity) return net2::invalid;
    if (capacity > max_headers + max_body) capacity = max_headers + max_body;
    size_t used = 0, expected = 0, header_scan = 3;
    bool have_headers = false;
    response parsed{};
    for (;;) {
        unsigned char extra = 0;
        const bool full = used == capacity || (have_headers && used == expected);
        const u32 available = full ? 1 : static_cast<u32>((capacity - used) < net2::payload_bytes ?
                                                         capacity - used : net2::payload_bytes);
        const i64 status = read(context, full ? &extra : buffer + used, available);
        if (status < 0) return status;
        if (static_cast<u64>(status) > available) return net2::io;
        if (full && status) return have_headers ? net2::invalid : net2::resources;
        used += static_cast<size_t>(status);
        // Each header byte is scanned once, including fragmented reads.
        bool header_complete = false;
        if (!have_headers) {
            const size_t limit = used < max_headers ? used : max_headers;
            for (; header_scan < limit; ++header_scan) {
                if (buffer[header_scan - 3] == '\r' && buffer[header_scan - 2] == '\n' &&
                    buffer[header_scan - 1] == '\r' && buffer[header_scan] == '\n') {
                    header_complete = true;
                    break;
                }
            }
        }
        if (header_complete || !status || (!have_headers && used >= max_headers)) {
            const error checked = parse_response(buffer, used, status == 0, parsed);
            if (checked != error::ok && checked != error::need_more) return parser_error(checked);
            if (parsed.body_offset) {
                expected = parsed.body_offset + parsed.body_length;
                have_headers = true;
                if (expected > capacity) return net2::resources;
            }
            if (!status) {
                if (checked != error::ok) return net2::io;
                result = parsed;
                return 0;
            }
        }
        if (have_headers && used > expected) return net2::invalid;
        if (!require_eof && have_headers && used == expected) {
            const error checked = parse_response(buffer, used, true, parsed);
            if (checked != error::ok) return parser_error(checked);
            result = parsed;
            return 0;
        }
    }
}
}
xos::i64 read_framed_response(response_reader read, void* context,
                              unsigned char* buffer, size_t capacity, response& result) {
    return read_response(read, context, buffer, capacity, result, true);
}
xos::i64 read_content_length_response(response_reader read, void* context,
                                      unsigned char* buffer, size_t capacity, response& result) {
    return read_response(read, context, buffer, capacity, result, false);
}

xos::i64 fetch(xos::net2::client& client, const url& input, unsigned char* buffer,
               size_t capacity, xos::u64 deadline, response& result, url& final_url,
               unsigned max_redirects) {
    using namespace xos;
    result = {}; final_url = {};
    if (!buffer || !capacity || max_redirects > 5) return net2::invalid;
    u32 original_address = 0;
    if (input.protocol != scheme::http || !net2::parse_ipv4(input.host, original_address)) return net2::unsupported;
    url current = input;
    unsigned redirects = 0;
    for (;;) {
        u32 address = 0;
        if (current.protocol != scheme::http || !net2::parse_ipv4(current.host, address)) return net2::unsupported;
        if (address != original_address || current.port != input.port) return net2::denied;
        char request[max_url + 512]; size_t request_length = 0;
        const error formatted = get_request(current, request, sizeof(request), request_length);
        if (formatted != error::ok) return parser_error(formatted);
        u64 handle = 0;
        i64 status = client.open(net2::protocol::tcp, address, current.port, deadline, handle);
        if (status) return status;
        for (size_t sent = 0; sent < request_length;) {
            status = client.write(handle, reinterpret_cast<const u8*>(request) + sent,
                                  static_cast<u32>(request_length - sent), deadline);
            if (status <= 0) return abandon(client, handle, deadline, status ? status : net2::io);
            sent += static_cast<size_t>(status);
        }
        response parsed{};
        struct tcp_read {
            net2::client& client;
            u64 handle, deadline;
        } source{client, handle, deadline};
        status = read_framed_response([](void* context, unsigned char* data, u32 length) {
            auto& tcp = *static_cast<tcp_read*>(context);
            return tcp.client.read(tcp.handle, data, length, tcp.deadline);
        }, &source, buffer, capacity, parsed);
        if (status) return abandon(client, handle, deadline, status);
        status = client.close_connection(handle, deadline);
        if (status) { client.close(); return status; }
        if (!is_redirect(parsed.status) || !max_redirects) {
            result = parsed; final_url = current; return 0;
        }
        if (redirects >= max_redirects) return net2::resources;
        url next{};
        const error redirected = redirect(current, parsed, redirects, next);
        if (redirected != error::ok) return parser_error(redirected);
        current = next;
    }
}
}
