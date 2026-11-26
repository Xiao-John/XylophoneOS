// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <mbedtls/ssl.h>
#include <xos/net_transport.hpp>

namespace native_tls {

enum class route_source { pinned, net2_dns };

// Single-use, single-threaded TLS 1.3 client. The caller supplies the trusted
// service identity, DER trust anchor, and DNS name independently of the address.
class stream {
public:
    stream();
    ~stream();
    stream(const stream&) = delete;
    stream& operator=(const stream&) = delete;

    int connect(xos::u64 service_pid, xos::u32 address, xos::u16 port,
                const char* hostname, const unsigned char* trust_anchor,
                size_t trust_anchor_size, xos::u64 deadline, route_source route = route_source::pinned);
    int write(const unsigned char* data, size_t size);
    // Zero is a verified TLS close_notify. Unauthenticated transport EOF fails.
    int read(unsigned char* data, size_t capacity);
    int finish();
    uint32_t verification_flags() const { return verify_flags_; }

private:
    static int send(void* context, const unsigned char* data, size_t size);
    static int receive(void* context, unsigned char* data, size_t size);
    int fail(int error);
    void release();

    xos::net2::client tcp_;
    mbedtls_x509_crt anchor_{};
    mbedtls_ssl_config config_{};
    mbedtls_ssl_context ssl_{};
    xos::u64 handle_ = 0;
    xos::u64 deadline_ = 0;
    uint32_t verify_flags_ = 0;
    bool started_ = false;
    bool verified_ = false;
    bool peer_closed_ = false;
};

}
