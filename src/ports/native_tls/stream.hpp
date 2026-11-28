// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <mbedtls/ssl.h>
#include <xos/net_transport.hpp>
#include "trust_store.hpp"

namespace native_tls {

enum class route_source { pinned, net2_dns };

struct peer_certificate_view {
    const unsigned char* data = nullptr;
    size_t size = 0;
};

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
    int connect(xos::u64 service_pid, xos::u32 address, xos::u16 port,
                const char* hostname, const trust_store& store,
                xos::u64 deadline, route_source route = route_source::pinned);
    int write(const unsigned char* data, size_t size);
    // Zero is a verified TLS close_notify. Unauthenticated transport EOF fails.
    int read(unsigned char* data, size_t capacity);
    int finish();
    // Read-only Net2 lease authority on this verified stream's original
    // session/deadline. No new session, reconnect or deadline extension.
    // Returns a Net2 status; a failed query retires the stream without replay.
    xos::i64 lease_status(xos::net2::lease_snapshot& snapshot);
    uint32_t verification_flags() const { return verify_flags_; }
    // Available after a verified handshake until finish or a fatal I/O error.
    // Copy the bytes before calling another stream operation or destroying it.
    [[nodiscard]] peer_certificate_view verified_peer_leaf_der() const;

private:
    int prepare(xos::u64 service_pid, xos::u32 address, xos::u16 port,
                const char* hostname, xos::u64 deadline);
    int handshake(xos::u64 service_pid, xos::u32 address, xos::u16 port,
                  const char* hostname, route_source route);
    static int send(void* context, const unsigned char* data, size_t size);
    static int receive(void* context, unsigned char* data, size_t size);
    xos::u64 request_deadline() const;
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
