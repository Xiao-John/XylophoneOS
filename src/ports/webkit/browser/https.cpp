// SPDX-License-Identifier: Apache-2.0
#include "https.hpp"
#include "tls_policy.hpp"
#include <openssl/ssl.h>
#include <openssl/x509v3.h>
#include <cstring>

namespace clarke_https {
namespace {
using namespace xos;
struct transport {
    net2::client client;
    u64 handle = 0, deadline = 0;
    u32 calls = 0, bytes = 0;
    bool ended = false;
    i64 error = 0;
    ~transport() {
        if (handle) (void)client.cancel_connection(handle, deadline);
        client.close();
    }
    bool permitted() {
        if (++calls > 4096 || bytes >= 512 * 1024) { error = net2::resources; return false; }
        const i64 clock = sdk::syscall(sys_clock_monotonic);
        if (clock < 0) { error = net2::io; return false; }
        if (static_cast<u64>(clock) >= deadline) { error = net2::timeout; return false; }
        return true;
    }
};
int bio_create(BIO* bio) { BIO_set_init(bio, 1); BIO_set_data(bio, nullptr); return 1; }
int bio_destroy(BIO* bio) { if (bio) { BIO_set_data(bio, nullptr); BIO_set_init(bio, 0); } return 1; }
int bio_read(BIO* bio, char* output, int length) {
    auto* state = static_cast<transport*>(BIO_get_data(bio));
    BIO_clear_retry_flags(bio);
    if (!state || !output || length <= 0 || !state->permitted()) return -1;
    const u32 budget = 512 * 1024 - state->bytes;
    const i64 result = state->client.read(state->handle, reinterpret_cast<u8*>(output),
        static_cast<u32>(length) < budget ? static_cast<u32>(length) : budget, state->deadline);
    if (result < 0) { state->error = result; return -1; }
    if (!result) state->ended = true;
    state->bytes += static_cast<u32>(result);
    return static_cast<int>(result);
}
int bio_write(BIO* bio, const char* input, int length) {
    auto* state = static_cast<transport*>(BIO_get_data(bio));
    BIO_clear_retry_flags(bio);
    if (!state || !input || length <= 0 || !state->permitted()) return -1;
    const u32 budget = 512 * 1024 - state->bytes;
    const i64 result = state->client.write(state->handle, reinterpret_cast<const u8*>(input),
        static_cast<u32>(length) < budget ? static_cast<u32>(length) : budget, state->deadline);
    if (result <= 0) { state->error = result ? result : net2::io; return -1; }
    state->bytes += static_cast<u32>(result);
    return static_cast<int>(result);
}
long bio_control(BIO* bio, int operation, long, void*) {
    if (operation == BIO_CTRL_FLUSH) return 1;
    auto* state = static_cast<transport*>(BIO_get_data(bio));
    if (operation == BIO_CTRL_EOF) return state && state->ended;
    return 0;
}
struct resources {
    BIO_METHOD* method = nullptr;
    SSL_CTX* context = nullptr;
    SSL* stream = nullptr;
    X509* anchor = nullptr;
    ~resources() { SSL_free(stream); SSL_CTX_free(context); X509_free(anchor); BIO_meth_free(method); }
};
}
i64 fetch(u64 service, const browser_http::url& target, unsigned char* buffer,
           std::size_t capacity, u64 deadline, browser_http::response& result)
{
    result = {};
    if (target.protocol != browser_http::scheme::https || target.port != clarke_tls_port ||
        std::strcmp(target.host, clarke_tls_host) || !buffer || !capacity) return net2::denied;
    transport native; native.deadline = deadline;
    i64 status = native.client.connect(service);
    if (status) return status;
    status = native.client.open(net2::protocol::tcp, clarke_tls_address, target.port, deadline, native.handle);
    if (status) return status;
    resources tls;
    tls.context = SSL_CTX_new(TLS_client_method());
    if (!tls.context || !SSL_CTX_set_min_proto_version(tls.context, TLS1_2_VERSION)) return net2::io;
    SSL_CTX_set_verify(tls.context, SSL_VERIFY_PEER, nullptr);
    SSL_CTX_set_verify_depth(tls.context, 8);
    const unsigned char* encoded = clarke_tls_anchor;
    tls.anchor = d2i_X509(nullptr, &encoded, sizeof(clarke_tls_anchor));
    if (!tls.anchor || encoded != clarke_tls_anchor + sizeof(clarke_tls_anchor) || X509_check_ca(tls.anchor) <= 0 ||
        X509_STORE_add_cert(SSL_CTX_get_cert_store(tls.context), tls.anchor) != 1) return net2::denied;
    tls.method = BIO_meth_new(BIO_TYPE_SOURCE_SINK | BIO_get_new_index(), "xos net2 bounded TLS");
    if (!tls.method || !BIO_meth_set_create(tls.method, bio_create) || !BIO_meth_set_destroy(tls.method, bio_destroy) ||
        !BIO_meth_set_read(tls.method, bio_read) || !BIO_meth_set_write(tls.method, bio_write) ||
        !BIO_meth_set_ctrl(tls.method, bio_control)) return net2::resources;
    tls.stream = SSL_new(tls.context);
    if (!tls.stream || SSL_set_tlsext_host_name(tls.stream, target.host) != 1 || SSL_set1_host(tls.stream, target.host) != 1)
        return net2::denied;
    X509_VERIFY_PARAM_set_hostflags(SSL_get0_param(tls.stream), X509_CHECK_FLAG_NO_PARTIAL_WILDCARDS);
    BIO* bio = BIO_new(tls.method);
    if (!bio) return net2::resources;
    BIO_set_data(bio, &native);
    SSL_set_bio(tls.stream, bio, bio);
    if (SSL_connect(tls.stream) != 1 || SSL_get_verify_result(tls.stream) != X509_V_OK)
        return native.error ? native.error : net2::denied;
    char request[browser_http::max_url + 512]; std::size_t length = 0;
    if (browser_http::get_request(target, request, sizeof(request), length) != browser_http::error::ok) return net2::invalid;
    for (std::size_t sent = 0; sent < length;) {
        std::size_t amount = 0;
        if (SSL_write_ex(tls.stream, request + sent, length - sent, &amount) != 1 || !amount)
            return native.error ? native.error : net2::io;
        sent += amount;
    }
    struct response_source { SSL* stream; transport& native; } source{tls.stream, native};
    status = browser_http::read_content_length_response([](void* context, unsigned char* data, u32 size) -> i64 {
        auto& source = *static_cast<response_source*>(context);
        std::size_t received = 0;
        const int result = SSL_read_ex(source.stream, data, size, &received);
        if (result == 1) return received ? static_cast<i64>(received) : net2::io;
        if (SSL_get_error(source.stream, result) == SSL_ERROR_ZERO_RETURN) return 0;
        return source.native.error ? source.native.error : net2::io;
    }, &source, buffer, capacity, result);
    if (status) { result = {}; return status; }
    // This BIO blocks within the original request deadline. The first local
    // shutdown may only send close_notify and return zero; the second receives
    // the peer's authenticated close. Zero is not an SSL_get_error input.
    if (!native.permitted()) { result = {}; return native.error; }
    int shutdown = SSL_shutdown(tls.stream);
    if (shutdown == 0 && native.permitted()) shutdown = SSL_shutdown(tls.stream);
    if (shutdown != 1) { result = {}; return native.error ? native.error : net2::io; }
    status = native.client.close_connection(native.handle, deadline);
    if (status) { result = {}; return status; }
    native.handle = 0;
    return 0;
}
}
