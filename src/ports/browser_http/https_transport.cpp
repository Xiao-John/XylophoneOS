// SPDX-License-Identifier: Apache-2.0
#include "https_transport.hpp"
#include "transport.hpp"

namespace browser_http {
xos::i64 fetch_https(const https_route& route, const url& target, unsigned char* buffer,
                     size_t capacity, xos::u64 deadline, response& result) {
    using namespace xos;
    result = {};
    if (target.protocol != scheme::https || !buffer || !capacity) return net2::invalid;

    char request[max_url + 512];
    size_t length = 0;
    if (get_request(target, request, sizeof request, length) != error::ok) return net2::invalid;

    native_tls::stream stream;
    const int connected = route.store
        ? stream.connect(route.service_pid, route.address, target.port, target.host,
                         *route.store, deadline, route.source)
        : stream.connect(route.service_pid, route.address, target.port, target.host,
                         route.trust_anchor, route.trust_anchor_size, deadline, route.source);
    if (connected) return connected;
    const auto* bytes = reinterpret_cast<const unsigned char*>(request);
    for (size_t sent = 0; sent < length;) {
        const int count = stream.write(bytes + sent, length - sent);
        if (count <= 0) return count ? count : net2::io;
        sent += static_cast<size_t>(count);
    }

    response parsed{};
    const i64 status = read_framed_response(
        [](void* context, unsigned char* data, u32 size) -> i64 {
            return static_cast<native_tls::stream*>(context)->read(data, size);
        }, &stream, buffer, capacity, parsed);
    if (status) return status;
    const int finished = stream.finish();
    if (finished) return finished;
    result = parsed;
    return 0;
}
}
