// SPDX-License-Identifier: Apache-2.0
#include "stream.hpp"

#include <psa/crypto.h>

namespace native_tls {
namespace {
int transport_result(xos::i64 count) {
    if (count >= 0) return static_cast<int>(count);
    if (count == xos::net2::timeout) return MBEDTLS_ERR_SSL_TIMEOUT;
    return MBEDTLS_ERR_SSL_INTERNAL_ERROR;
}

xos::u32 chunk_size(size_t size) {
    return size < xos::net2::payload_bytes ? static_cast<xos::u32>(size)
        : xos::net2::payload_bytes;
}

bool valid_dns_name(const char* hostname) {
    if (!hostname) return false;
    size_t label = 0;
    bool alphanumeric = false;
    for (size_t i = 0; i <= 253; ++i) {
        const char ch = hostname[i];
        if (!ch) return label && alphanumeric;
        if (ch == '.') {
            if (!label || !alphanumeric) return false;
            label = 0;
            continue;
        }
        alphanumeric = (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') ||
            (ch >= '0' && ch <= '9');
        if ((!alphanumeric && (ch != '-' || !label)) || ++label > 63)
            return false;
    }
    return false;
}
}

stream::stream() {
    mbedtls_x509_crt_init(&anchor_);
    mbedtls_ssl_config_init(&config_);
    mbedtls_ssl_init(&ssl_);
}

stream::~stream() {
    release();
    mbedtls_ssl_free(&ssl_);
    mbedtls_ssl_config_free(&config_);
    mbedtls_x509_crt_free(&anchor_);
}

int stream::connect(xos::u64 service_pid, xos::u32 address, xos::u16 port,
                    const char* hostname, const unsigned char* trust_anchor,
                    size_t trust_anchor_size, xos::u64 deadline, route_source route) {
    if (!trust_anchor || !trust_anchor_size || trust_anchor_size > max_trust_anchor_bytes)
        return MBEDTLS_ERR_SSL_BAD_INPUT_DATA;
    int status = prepare(service_pid, address, port, hostname, deadline);
    if (!status) status = mbedtls_x509_crt_parse_der(&anchor_, trust_anchor, trust_anchor_size);
    return status ? status : handshake(service_pid, address, port, hostname, route);
}

int stream::connect(xos::u64 service_pid, xos::u32 address, xos::u16 port,
                    const char* hostname, const trust_store& store,
                    xos::u64 deadline, route_source route) {
    if (!store.ready()) return MBEDTLS_ERR_SSL_BAD_INPUT_DATA;
    int status = prepare(service_pid, address, port, hostname, deadline);
    if (!status) status = store.copy_to(&anchor_);
    return status ? status : handshake(service_pid, address, port, hostname, route);
}

int stream::prepare(xos::u64 service_pid, xos::u32 address, xos::u16 port,
                    const char* hostname, xos::u64 deadline) {
    if (started_ || !service_pid || !address || !port || !valid_dns_name(hostname))
        return MBEDTLS_ERR_SSL_BAD_INPUT_DATA;
    started_ = true;
    deadline_ = deadline;
    const auto now = xos::sdk::syscall(xos::sys_clock_monotonic);
    if (now < 0 || deadline <= static_cast<xos::u64>(now) ||
        deadline - static_cast<xos::u64>(now) > xos::net2::max_request_ns)
        return MBEDTLS_ERR_SSL_BAD_INPUT_DATA;
    if (xos_tls_wall_time(nullptr) < 0 || psa_crypto_init() != PSA_SUCCESS)
        return MBEDTLS_ERR_SSL_INTERNAL_ERROR;
    return 0;
}

int stream::handshake(xos::u64 service_pid, xos::u32 address, xos::u16 port,
                      const char* hostname, route_source route) {
    int status = mbedtls_ssl_config_defaults(&config_, MBEDTLS_SSL_IS_CLIENT,
                                         MBEDTLS_SSL_TRANSPORT_STREAM, MBEDTLS_SSL_PRESET_DEFAULT);
    if (status) return status;
    mbedtls_ssl_conf_min_tls_version(&config_, MBEDTLS_SSL_VERSION_TLS1_3);
    mbedtls_ssl_conf_max_tls_version(&config_, MBEDTLS_SSL_VERSION_TLS1_3);
    mbedtls_ssl_conf_authmode(&config_, MBEDTLS_SSL_VERIFY_REQUIRED);
    mbedtls_ssl_conf_ca_chain(&config_, &anchor_, nullptr);
    status = mbedtls_ssl_setup(&ssl_, &config_);
    if (status) return status;
    status = mbedtls_ssl_set_hostname(&ssl_, hostname);
    if (status) return status;
    auto network = tcp_.connect(service_pid);
    if (!network && route == route_source::net2_dns) {
        xos::u32 length = 0;
        while (hostname[length]) ++length;
        xos::net2::resolve_reply answer{};
        network = tcp_.resolve_ipv4(hostname, length, deadline_, answer);
        if (network) return fail(static_cast<int>(network));
        if (answer.address != address) return fail(static_cast<int>(xos::net2::denied));
        address = answer.address;
    }
    if (!network)
        network = tcp_.open(xos::net2::protocol::tcp, address, port, deadline_, handle_);
    if (network) return fail(transport_result(network));
    mbedtls_ssl_set_bio(&ssl_, this, send, receive, nullptr);
    status = mbedtls_ssl_handshake(&ssl_);
    verify_flags_ = mbedtls_ssl_get_verify_result(&ssl_);
    if (status) return fail(status);
    if (verify_flags_) return fail(MBEDTLS_ERR_X509_CERT_VERIFY_FAILED);
    verified_ = true;
    return 0;
}

peer_certificate_view stream::verified_peer_leaf_der() const {
    if (!verified_) return {};
    const auto* certificate = mbedtls_ssl_get_peer_cert(&ssl_);
    if (!certificate || !certificate->raw.p || !certificate->raw.len) return {};
    return { certificate->raw.p, certificate->raw.len };
}

int stream::write(const unsigned char* data, size_t size) {
    if (!verified_ || peer_closed_ || !data || !size) return MBEDTLS_ERR_SSL_BAD_INPUT_DATA;
    const int count = mbedtls_ssl_write(&ssl_, data, size);
    return count > 0 ? count : fail(count ? count : MBEDTLS_ERR_SSL_INTERNAL_ERROR);
}

int stream::read(unsigned char* data, size_t capacity) {
    if (!verified_ || !data || !capacity) return MBEDTLS_ERR_SSL_BAD_INPUT_DATA;
    if (peer_closed_) return 0;
    const int count = mbedtls_ssl_read(&ssl_, data, capacity);
    if (count == MBEDTLS_ERR_SSL_PEER_CLOSE_NOTIFY) {
        peer_closed_ = true;
        return 0;
    }
    return count > 0 ? count : fail(count ? count : MBEDTLS_ERR_SSL_CONN_EOF);
}

int stream::finish() {
    if (!verified_ || !peer_closed_) return MBEDTLS_ERR_SSL_BAD_INPUT_DATA;
    const int status = mbedtls_ssl_close_notify(&ssl_);
    if (status) return fail(status);
    const auto network = tcp_.close_connection(handle_, deadline_);
    if (network) return fail(transport_result(network));
    handle_ = 0;
    verified_ = false;
    tcp_.close();
    return 0;
}

int stream::send(void* context, const unsigned char* data, size_t size) {
    auto& self = *static_cast<stream*>(context);
    return transport_result(self.tcp_.write(self.handle_, data, chunk_size(size), self.deadline_));
}

int stream::receive(void* context, unsigned char* data, size_t size) {
    auto& self = *static_cast<stream*>(context);
    return transport_result(self.tcp_.read(self.handle_, data, chunk_size(size), self.deadline_));
}

int stream::fail(int error) {
    verified_ = false;
    release();
    return error;
}

void stream::release() {
    if (handle_) {
        (void) tcp_.cancel_connection(handle_, deadline_);
        handle_ = 0;
    }
    tcp_.close();
}
}
