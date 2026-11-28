// SPDX-License-Identifier: Apache-2.0
#include "../../src/ports/browser_http/transport.hpp"
#include <algorithm>
#include <cassert>
#include <string>
#include <vector>

using namespace browser_http;
struct source { std::string wire; size_t pos = 0; size_t fragment = 37; };
struct output { std::vector<unsigned char> bytes; bool fail = false; };
static xos::i64 read_bytes(void* ctx, unsigned char* out, xos::u32 cap) {
    auto& s = *static_cast<source*>(ctx);
    const size_t n = std::min({size_t(cap), s.fragment, s.wire.size() - s.pos});
    for (size_t i = 0; i < n; ++i) out[i] = static_cast<unsigned char>(s.wire[s.pos++]);
    return static_cast<xos::i64>(n);
}
static xos::i64 write_bytes(void* ctx, const unsigned char* data, xos::u32 n) {
    auto& out = *static_cast<output*>(ctx);
    if (out.fail) return -77;
    out.bytes.insert(out.bytes.end(), data, data + n);
    return n;
}
static xos::i64 run(source& s, output& o, size_t limit, response& r) {
    std::vector<unsigned char> headers(max_headers);
    return read_streamed_response(read_bytes, &s, write_bytes, &o, headers.data(), headers.size(), limit, r);
}
int main() {
    const size_t size = 2 * 1024 * 1024 + 7;
    const std::string head = "HTTP/1.1 200 OK\r\nContent-Length: " + std::to_string(size) + "\r\n\r\n";
    const std::string wire = head + std::string(size, 'z');
    response result{};
    source good{wire}; output out;
    assert(run(good, out, size, result) == 0 && out.bytes.size() == size && result.body_length == size);
    source oversize{wire}; output refused;
    assert(run(oversize, refused, size - 1, result) == xos::net2::resources && refused.bytes.empty());
    source short_input{wire.substr(0, wire.size() - 1)}; output truncated;
    assert(run(short_input, truncated, size, result) == xos::net2::io);
    source extra{wire + "x"}; output excessive;
    assert(run(extra, excessive, size, result) == xos::net2::invalid);
    source duplicate{"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nContent-Length: 0\r\n\r\n"}; output invalid;
    assert(run(duplicate, invalid, size, result) == xos::net2::invalid);
    source chunked{"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n"}; output unsupported;
    assert(run(chunked, unsupported, size, result) == xos::net2::unsupported);
    source failure{wire}; output broken; broken.fail = true;
    assert(run(failure, broken, size, result) == -77);
    source empty{"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"}; output zero;
    assert(run(empty, zero, 0, result) == 0 && zero.bytes.empty());
}
